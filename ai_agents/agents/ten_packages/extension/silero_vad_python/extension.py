#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    AudioFrame,
    AudioFrameDataFmt,
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    StatusCode,
    CmdResult,
    Data,
)
from .config import SileroVADConfig
from .funasr_model import get_asr_wrapper

import numpy as np
import os
import json
import time
from typing import Dict, List

BYTES_PER_SAMPLE = 2


class SileroVADPythonExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name
        self.config: SileroVADConfig = None

        # Silero VAD model and iterator
        self.model = None
        self.vad_iterator = None

        # Audio buffer for processing
        self.audio_buffer: bytearray = bytearray()

        # VAD state tracking
        self.is_speech_active = False
        self.current_start_ms = 0
        self.total_samples_processed = 0

        # ASR (Speech Recognition) related
        self.asr_model = None
        self.speech_buffer: bytearray = bytearray()
        self.interruption_keywords: Dict[str, List[str]] = {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": [],
        }

        # Speech segment buffer for saving detected speech segments as WAV
        self.speech_segment_buffer: bytearray = bytearray()
        self.speech_segment_count: int = 0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        config_json, _ = await ten_env.get_property_to_json("")
        self.config = SileroVADConfig.model_validate_json(config_json)
        ten_env.log_debug(f"config: {self.config}")

        # Validate sampling rate
        if self.config.sampling_rate not in (8000, 16000):
            ten_env.log_error(
                f"Invalid sampling_rate: {self.config.sampling_rate}. Must be 8000 or 16000"
            )
            raise ValueError(
                f"sampling_rate must be 8000 or 16000, got {self.config.sampling_rate}"
            )

        ten_env.log_info(
            f"Silero VAD config: threshold={self.config.threshold}, "
            f"min_speech={self.config.min_speech_duration_ms}ms, "
            f"min_silence={self.config.min_silence_duration_ms}ms, "
            f"use_onnx={self.config.use_onnx}"
        )

        self._load_model(ten_env)

    def _load_model(self, ten_env: AsyncTenEnv) -> None:
        """Load Silero VAD model and create iterator."""
        try:
            from silero_vad import load_silero_vad, VADIterator
        except ImportError:
            ten_env.log_error(
                "silero-vad is not installed. Install with: pip install silero-vad torch torchaudio"
            )
            raise ImportError("silero-vad package is required")

        ten_env.log_info(f"Loading Silero VAD model (ONNX: {self.config.use_onnx})...")

        try:
            self.model = load_silero_vad(onnx=self.config.use_onnx)
        except Exception as e:
            if self.config.use_onnx:
                ten_env.log_warn(
                    f"Failed to load ONNX model: {e}. Falling back to JIT model..."
                )
                self.model = load_silero_vad(onnx=False)
            else:
                raise

        self.vad_iterator = VADIterator(
            self.model,
            threshold=self.config.threshold,
            sampling_rate=self.config.sampling_rate,
            min_silence_duration_ms=self.config.min_silence_duration_ms,
            speech_pad_ms=self.config.speech_pad_ms,
        )

        ten_env.log_info("Silero VAD model loaded successfully")

        # Load ASR model if enabled
        if self.config.enable_asr:
            self._load_asr_model(ten_env)
            self._load_interruption_keywords(ten_env)

    def _load_asr_model(self, ten_env: AsyncTenEnv) -> None:
        """Load FunASR model for speech recognition."""
        try:
            ten_env.log_info(f"Loading FunASR model from: {self.config.asr_model_dir}")
            self.asr_model = get_asr_wrapper(
                model_dir=self.config.asr_model_dir, quantize=self.config.asr_quantize
            )
            ten_env.log_info("FunASR model loaded successfully")
        except Exception as e:
            ten_env.log_error(f"Failed to load FunASR model: {e}")
            ten_env.log_warn("ASR functionality will be disabled")
            self.asr_model = None

    def _load_interruption_keywords(self, ten_env: AsyncTenEnv) -> None:
        """Load interruption keywords from JSON file."""
        keywords_file = self.config.interruption_keywords_file

        # If relative path, resolve relative to extension directory
        if not os.path.isabs(keywords_file):
            extension_dir = os.path.dirname(os.path.abspath(__file__))
            keywords_file = os.path.join(extension_dir, keywords_file)

        try:
            with open(keywords_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                keywords = data.get("keywords", {})
                self.interruption_keywords["high_priority"] = keywords.get(
                    "high_priority", {}
                ).get("keywords", [])
                self.interruption_keywords["medium_priority"] = keywords.get(
                    "medium_priority", {}
                ).get("keywords", [])
                self.interruption_keywords["low_priority"] = keywords.get(
                    "low_priority", {}
                ).get("keywords", [])

            ten_env.log_info(
                f"Loaded interruption keywords: "
                f"high={len(self.interruption_keywords['high_priority'])}, "
                f"medium={len(self.interruption_keywords['medium_priority'])}, "
                f"low={len(self.interruption_keywords['low_priority'])}"
            )
        except FileNotFoundError:
            ten_env.log_warn(f"Interruption keywords file not found: {keywords_file}")
        except json.JSONDecodeError as e:
            ten_env.log_error(f"Failed to parse interruption keywords file: {e}")
        except Exception as e:
            ten_env.log_error(f"Error loading interruption keywords: {e}")

    async def on_start(self, _ten_env: AsyncTenEnv) -> None:
        self._reset_state()
        _ten_env.log_info("Silero VAD extension started")

    async def on_stop(self, _ten_env: AsyncTenEnv) -> None:
        self._reset_state()
        _ten_env.log_info("Silero VAD extension stopped")

    async def on_deinit(self, _ten_env: AsyncTenEnv) -> None:
        self.model = None
        self.vad_iterator = None

    def _reset_state(self) -> None:
        """Reset VAD state and audio buffer."""
        self.audio_buffer = bytearray()
        self.speech_buffer = bytearray()
        self.speech_segment_buffer = bytearray()
        self.is_speech_active = False
        self.current_start_ms = 0
        self.total_samples_processed = 0
        if self.vad_iterator is not None:
            self.vad_iterator.reset_states()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd name: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        pass

    async def _send_audio_frame(self, ten_env: AsyncTenEnv, audio_data: bytes) -> None:
        """Helper function to create and send an audio frame with given data."""

        # Dump output audio if needed
        self._dump_audio_if_needed(audio_data, "out")

        audio_frame = AudioFrame.create("pcm_frame")
        audio_frame.set_bytes_per_sample(BYTES_PER_SAMPLE)
        audio_frame.set_sample_rate(self.config.sampling_rate)
        audio_frame.set_number_of_channels(1)
        audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
        audio_frame.set_samples_per_channel(len(audio_data) // BYTES_PER_SAMPLE)
        audio_frame.alloc_buf(len(audio_data))
        buf = audio_frame.lock_buf()
        buf[:] = audio_data
        audio_frame.unlock_buf(buf)
        await ten_env.send_audio_frame(audio_frame)

    def _dump_audio_if_needed(self, buf: bytes, suffix: str) -> None:
        if not self.config.dump:
            return

        if not self.config.dump_path:
            return

        dump_file = os.path.join(self.config.dump_path, f"{self.name}_{suffix}.pcm")
        # Create directory if it doesn't exist
        os.makedirs(self.config.dump_path, exist_ok=True)
        with open(dump_file, "ab") as f:
            f.write(buf)

    async def _process_vad_result(self, ten_env: AsyncTenEnv, result: dict) -> None:
        """Process VAD detection result and send appropriate commands."""

        if "start" in result:
            # Speech start detected
            if not self.is_speech_active:
                self.is_speech_active = True
                self.current_start_ms = result["start"]
                self._speech_start_time = time.time() * 1000  # 记录实际时间
                ten_env.log_info("[VAD] Speech START")

                # Clear speech segment buffer for new segment
                self.speech_segment_buffer = bytearray()

                # Send start_of_sentence command
                await ten_env.send_cmd(Cmd.create("start_of_sentence"))

        elif "end" in result:
            # Speech end detected
            if self.is_speech_active:
                self.is_speech_active = False
                # 使用实际时间计算时长
                actual_duration_ms = int(time.time() * 1000 - self._speech_start_time)
                vad_duration_ms = result["end"] - self.current_start_ms
                ten_env.log_info(
                    f"[VAD] Speech END (actual: {actual_duration_ms}ms, vad: {vad_duration_ms}ms)"
                )

                # Send end_of_sentence command
                await ten_env.send_cmd(Cmd.create("end_of_sentence"))

                # Save speech segment as WAV file
                self._save_speech_segment_as_wav(ten_env, actual_duration_ms)

                # Trigger ASR if enabled and speech buffer has data
                if self.config.enable_asr and self.asr_model is not None:
                    await self._process_asr_interruption(ten_env)

    def _save_speech_segment_as_wav(
        self, ten_env: AsyncTenEnv, duration_ms: int
    ) -> None:
        """Save detected speech segment to a WAV file."""
        if not self.config.dump:
            return

        if not self.config.dump_path:
            return

        if not self.speech_segment_buffer:
            return

        import datetime
        import wave

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.name}_speech_{self.speech_segment_count}_{timestamp}_{duration_ms}ms.wav"
        dump_file = os.path.join(self.config.dump_path, filename)

        # Ensure dump directory exists
        os.makedirs(self.config.dump_path, exist_ok=True)

        # Write WAV file
        with wave.open(dump_file, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.config.sampling_rate)
            wav_file.writeframes(bytes(self.speech_segment_buffer))

        ten_env.log_info(
            f"Saved speech segment: {filename} ({len(self.speech_segment_buffer)} bytes)"
        )
        self.speech_segment_count += 1
        self.speech_segment_buffer = bytearray()

    def _check_interruption(self, text: str) -> Dict[str, any]:
        """
        Check if the recognized text contains interruption keywords.

        Args:
            text: Recognized text from ASR

        Returns:
            Dict with keys:
                - detected: bool - Whether interruption was detected
                - priority: str - The priority level (high/medium/low)
                - matched_keyword: str - The matched keyword

        """
        if not text:
            return {"detected": False, "priority": None, "matched_keyword": None}

        text_lower = text.lower()

        # Determine which priority levels to check based on threshold
        threshold = self.config.interruption_threshold
        priorities_to_check = []

        if threshold == "low":
            priorities_to_check = ["high_priority", "medium_priority", "low_priority"]
        elif threshold == "medium":
            priorities_to_check = ["high_priority", "medium_priority"]
        else:  # high
            priorities_to_check = ["high_priority"]

        # Check keywords in priority order
        for priority in priorities_to_check:
            for keyword in self.interruption_keywords[priority]:
                if keyword.lower() in text_lower:
                    return {
                        "detected": True,
                        "priority": priority.replace("_priority", ""),
                        "matched_keyword": keyword,
                    }

        return {"detected": False, "priority": None, "matched_keyword": None}

    async def _process_asr_interruption(self, ten_env: AsyncTenEnv) -> None:
        """
        Process ASR recognition on speech buffer and check for interruption.
        Called when VAD detects speech end.
        """
        if not self.speech_buffer:
            ten_env.log_debug("No speech buffer to process for ASR")
            return

        speech_bytes = bytes(self.speech_buffer)
        buffer_size_ms = len(speech_bytes) / (2 * self.config.sampling_rate) * 1000

        ten_env.log_info(
            f"ASR: Processing speech buffer: {len(speech_bytes)} bytes "
            f"({buffer_size_ms:.1f}ms)"
        )

        try:
            # Recognize speech
            result = self.asr_model.recognize(speech_bytes, self.config.sampling_rate)
            text = self.asr_model.extract_text(result)

            if text:
                ten_env.log_info(f"ASR recognized text: {text}")

                # Check for interruption keywords
                interruption = self._check_interruption(text)

                if interruption["detected"]:
                    ten_env.log_info(
                        f"Interruption detected! Priority: {interruption['priority']}, "
                        f"Matched keyword: '{interruption['matched_keyword']}'"
                    )

                    # Send interruption_detected command with details
                    cmd = Cmd.create("interruption_detected")
                    cmd.set_property_string("text", text)
                    cmd.set_property_string("priority", interruption["priority"])
                    cmd.set_property_string(
                        "matched_keyword", interruption["matched_keyword"]
                    )
                    await ten_env.send_cmd(cmd)
                else:
                    ten_env.log_debug("No interruption keywords detected")
            else:
                ten_env.log_debug("ASR: No text recognized from speech buffer")

        except Exception as e:
            ten_env.log_error(f"ASR processing error: {e}")
        finally:
            # Clear speech buffer after processing
            self.speech_buffer = bytearray()

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        # Skip processing if VAD iterator is not ready yet
        if self.vad_iterator is None:
            return

        frame_buf = audio_frame.get_buf()
        frame_size_ms = len(frame_buf) / (self.config.sampling_rate * 2) * 1000

        # Log frame size info occasionally
        if self.total_samples_processed % 1000 < len(frame_buf) // 2:
            ten_env.log_info(
                f"[VAD] Audio frame: {len(frame_buf)} bytes, {frame_size_ms:.1f}ms, "
                f"sample_rate={self.config.sampling_rate}, is_speech_active={self.is_speech_active}"
            )
        self.total_samples_processed += len(frame_buf) // 2

        frame_buf = audio_frame.get_buf()
        self._dump_audio_if_needed(frame_buf, "in")

        # Optional passthrough - forward audio ONLY when speech is detected
        if self.config.passthrough and self.is_speech_active:
            if not hasattr(self, '_forwarded_frame_count'):
                self._forwarded_frame_count = 0
            self._forwarded_frame_count += 1
            if self._forwarded_frame_count == 1:
                ten_env.log_info(f"[VAD] >>>> First frame forwarded to STT: {len(frame_buf)} bytes")
            elif self._forwarded_frame_count % 100 == 0:
                ten_env.log_info(f"[VAD] Forwarded {self._forwarded_frame_count} frames to STT")
            await self._send_audio_frame(ten_env, frame_buf)

        # Cache audio for speech segment saving
        if self.is_speech_active and self.config.dump:
            self.speech_segment_buffer.extend(frame_buf)

        # Cache audio for ASR when enabled
        if self.config.enable_asr:
            # Always cache audio (we keep a rolling buffer)
            # During speech activity, this captures the speech segment
            # We also keep some audio before speech starts (context window)
            max_buffer_ms = 10000  # Keep up to 10 seconds of audio
            max_buffer_bytes = int(max_buffer_ms * self.config.sampling_rate * 2 / 1000)
            self.speech_buffer.extend(frame_buf)

            # Trim buffer if too large (FIFO)
            if len(self.speech_buffer) > max_buffer_bytes:
                excess = len(self.speech_buffer) - max_buffer_bytes
                self.speech_buffer = self.speech_buffer[excess:]

        # Accumulate audio buffer for VAD processing
        self.audio_buffer.extend(frame_buf)

        # Check if we have enough data for a chunk
        chunk_bytes = self.config.chunk_size * BYTES_PER_SAMPLE
        if len(self.audio_buffer) < chunk_bytes:
            return

        # Extract chunk
        audio_buf = bytes(self.audio_buffer[:chunk_bytes])
        self.audio_buffer = self.audio_buffer[chunk_bytes:]

        # Convert int16 PCM to float32 normalized to [-1, 1]
        audio_int16 = np.frombuffer(audio_buf, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Process with Silero VAD
        result = self.vad_iterator(audio_float32, return_seconds=False)

        if result:
            await self._process_vad_result(ten_env, result)
