#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import datetime
import wave
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

import numpy as np
import os

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

        # ASR (Speech Recognition) related
        self.asr_model = None
        self.speech_buffer: bytearray = bytearray()

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
            f"use_onnx={self.config.use_onnx}",
            f"dump={self.config.dump}",
        )

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

    async def _process_vad_result(self, ten_env: AsyncTenEnv, result: dict) -> None:
        """Process VAD detection result and send appropriate commands."""
        if "start" in result:
            # Speech start detected
            if not self.is_speech_active:
                self.is_speech_active = True
                self.current_start_ms = result["start"]
                ten_env.log_info("[VAD] Speech START")
                # Clear speech segment buffer for new segment
                self.speech_segment_buffer = bytearray()
                # Send start_of_sentence command
                ten_env.log_info("[VAD] Sending start_of_sentence command")
                await ten_env.send_cmd(Cmd.create("start_of_sentence"))
                ten_env.log_info("[VAD] Command sent: start_of_sentence")
        elif "end" in result:
            # Speech end detected
            if self.is_speech_active:
                self.is_speech_active = False
                # 使用实际时间计算时长
                ten_env.log_info("[VAD] Speech END")
                # Send end_of_sentence command
                ten_env.log_info("[VAD] Sending end_of_sentence command")
                await ten_env.send_cmd(Cmd.create("end_of_sentence"))
                ten_env.log_info("[VAD] Command sent: end_of_sentence")
                # Save speech segment as WAV file
                self._save_speech_segment_as_wav(ten_env)

    def _save_speech_segment_as_wav(self, ten_env: AsyncTenEnv) -> None:
        """Save detected speech segment to a WAV file."""
        if not self.config.dump:
            return

        if not self.config.dump_path:
            return

        if not self.speech_segment_buffer:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.name}_speech_{self.speech_segment_count}_{timestamp}.wav"
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

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        # Skip processing if VAD iterator is not ready yet
        if self.vad_iterator is None:
            return

        frame_buf = audio_frame.get_buf()  # 固定 320 bytes

        # Debug: log frame count every 100 frames
        if not hasattr(self, "_frame_count"):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 100 == 0:
            ten_env.log_debug(
                f"[VAD] Frame #{self._frame_count}: {len(frame_buf)} bytes"
            )

        # Optional passthrough - forward audio ONLY when speech is detected
        if self.config.passthrough and self.is_speech_active:
            if not hasattr(self, "_forwarded_frame_count"):
                self._forwarded_frame_count = 0
            self._forwarded_frame_count += 1
            if self._forwarded_frame_count == 1:
                ten_env.log_info(
                    f"[VAD] >>>> First frame forwarded to STT: {len(frame_buf)} bytes"
                )
            elif self._forwarded_frame_count % 100 == 0:
                ten_env.log_info(
                    f"[VAD] Forwarded {self._forwarded_frame_count} frames to STT"
                )
            await self._send_audio_frame(ten_env, frame_buf)

        # Cache audio for speech segment saving
        if self.is_speech_active and self.config.dump:
            self.speech_segment_buffer.extend(frame_buf)

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

        # Debug: before VAD inference
        # ten_env.log_info(f"[VAD] Processing chunk: {len(audio_buf)} bytes")

        # Process with Silero VAD
        result = self.vad_iterator(audio_float32, return_seconds=False)

        if result:
            # Debug: VAD result
            ten_env.log_info(f"[VAD] Result: {result}")
            await self._process_vad_result(ten_env, result)
