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
)
from .config import FSMNVADConfig

import numpy as np
import os

BYTES_PER_SAMPLE = 2


class SileroVADPythonExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name
        self.config: FSMNVADConfig = None

        # FSMN VAD model
        self.model = None
        self.vad_cache: dict = {}

        # Audio buffer for processing
        self.audio_buffer: bytearray = bytearray()

        # Pre-buffer for speech start (retains recent audio before VAD detection)
        self.pre_buffer: bytearray = bytearray()
        self.pre_buffer_bytes: int = 0

        # Chunk size in samples (computed from chunk_size_ms)
        self.chunk_samples: int = 0

        # VAD state tracking
        self.is_speech_active = False

        # WebRTC AudioProcessing (AGC + NS)
        self.audio_processor = None

        # Speech segment buffer for saving detected speech segments as WAV
        self.speech_segment_buffer: bytearray = bytearray()
        self.speech_segment_count: int = 0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        config_json, _ = await ten_env.get_property_to_json("")
        self.config = FSMNVADConfig.model_validate_json(config_json)
        ten_env.log_debug(f"config: {self.config}")

        # Validate sampling rate
        if self.config.sampling_rate != 16000:
            ten_env.log_error(
                f"Invalid sampling_rate: {self.config.sampling_rate}. Must be 16000 for FSMN VAD"
            )
            raise ValueError(
                f"sampling_rate must be 16000 for FSMN VAD, got {self.config.sampling_rate}"
            )

        # Compute chunk size in samples
        self.chunk_samples = int(
            self.config.chunk_size_ms * self.config.sampling_rate / 1000
        )

        # Compute pre-buffer size in bytes
        self.pre_buffer_bytes = (
            int(self.config.pre_buffer_ms * self.config.sampling_rate / 1000)
            * BYTES_PER_SAMPLE
        )

        ten_env.log_info(
            f"FSMN VAD config: model_dir={self.config.model_dir}, "
            f"chunk_size_ms={self.config.chunk_size_ms}, "
            f"chunk_samples={self.chunk_samples}, "
            f"device={self.config.device}, "
            f"passthrough={self.config.passthrough}, "
            f"dump={self.config.dump}"
        )

        # Load model
        self._load_model(ten_env)

        # Initialize AGC + NS
        self._init_audio_processor(ten_env)

    def _load_model(self, ten_env: AsyncTenEnv) -> None:
        """Load FunASR FSMN VAD model."""
        try:
            from funasr import AutoModel
        except ImportError:
            ten_env.log_error(
                "funasr is not installed. Install with: pip install funasr"
            )
            raise ImportError("funasr package is required")

        model_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            self.config.model_dir,
        )
        ten_env.log_info(f"Loading FSMN VAD model from: {model_path}")

        self.model = AutoModel(
            model=model_path,
            device=self.config.device,
            disable_update=True,
            disable_pbar=True,
            # lookback_time_start_point=200,  # 起点向前冗余
            # lookahead_time_end_point=100,  # 终点向后冗余
            # do_extend=1,  # 是否启用上述扩展
            max_end_silence_time=1000,  # 静音断句阈值
        )
        self.vad_cache = {}

        ten_env.log_info("FSMN VAD model loaded successfully")

    def _init_audio_processor(self, ten_env: AsyncTenEnv) -> None:
        """Initialize WebRTC AudioProcessing for AGC + NS."""
        if not self.config.enable_agc and not self.config.enable_ns:
            ten_env.log_info("AGC and NS both disabled, skipping")
            return

        try:
            from webrtc_audio_processing import AudioProcessingModule
        except ImportError:
            ten_env.log_warn(
                "webrtc-audio-processing not installed, AGC/NS disabled"
            )
            return

        self.audio_processor = AudioProcessingModule(
            aec_type=0,
            enable_ns=self.config.enable_ns,
            agc_type=self.config.agc_level if self.config.enable_agc else 0,
            enable_vad=False,
        )
        self.audio_processor.set_stream_format(self.config.sampling_rate, 1)
        if self.config.enable_ns:
            self.audio_processor.set_ns_level(self.config.ns_level)
        self.audio_processor.set_system_delay(0)

        ten_env.log_info(
            f"AudioProcessing initialized: agc={self.config.enable_agc}, "
            f"ns={self.config.enable_ns}, agc_level={self.config.agc_level}, "
            f"ns_level={self.config.ns_level}"
        )

    async def on_start(self, _ten_env: AsyncTenEnv) -> None:
        self._reset_state()
        _ten_env.log_info("FSMN VAD extension started")

    async def on_stop(self, _ten_env: AsyncTenEnv) -> None:
        self._reset_state()
        _ten_env.log_info("FSMN VAD extension stopped")

    async def on_deinit(self, _ten_env: AsyncTenEnv) -> None:
        self.model = None
        self.vad_cache = {}

    def _reset_state(self) -> None:
        """Reset VAD state and audio buffer."""
        self.audio_buffer = bytearray()
        self.pre_buffer = bytearray()
        self.speech_segment_buffer = bytearray()
        self.is_speech_active = False
        self.vad_cache = {}

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd name: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    def _dump_audio_if_needed(self, buf: bytes, suffix: str) -> None:
        if not self.config.dump:
            return
        if not self.config.dump_path:
            return
        dump_file = os.path.join(
            self.config.dump_path, f"{self.name}_{suffix}.pcm"
        )
        with open(dump_file, "ab") as f:
            f.write(buf)

    async def _send_audio_frame(self, ten_env: AsyncTenEnv, audio_data: bytes) -> None:
        """Helper function to create and send an audio frame with given data."""

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

    async def _process_vad_result(self, ten_env: AsyncTenEnv, segments: list) -> None:
        """Process FSMN VAD detection result and send appropriate commands.

        FSMN output format (list of [beg, end] pairs):
        - [[beg, -1]]: speech start detected
        - [[-1, end]]: speech end detected
        - [[beg, end]]: complete segment (both start and end)
        - []: no event
        Timestamps are in milliseconds.
        """
        if not segments:
            return

        for segment in segments:
            beg, end = segment[0], segment[1]

            # Speech start detected
            if beg != -1 and not self.is_speech_active:
                # Send pre-buffered audio to ASR first
                if self.config.passthrough and self.pre_buffer:
                    pre_buf_bytes = bytes(self.pre_buffer)
                    ten_env.log_info(
                        f"[VAD] Sending pre-buffer: {len(pre_buf_bytes)} bytes "
                        f"(~{len(pre_buf_bytes) / (self.config.sampling_rate / 1000 * BYTES_PER_SAMPLE):.0f}ms)"
                    )
                    await self._send_audio_frame(ten_env, pre_buf_bytes)
                    self.pre_buffer = bytearray()
                self.is_speech_active = True
                ten_env.log_info(f"[VAD] Speech START at {beg}ms")
                self.speech_segment_buffer = bytearray()
                await ten_env.send_cmd(Cmd.create("start_of_sentence"))

            # Speech end detected
            if end != -1 and self.is_speech_active:
                self.is_speech_active = False
                ten_env.log_info(f"[VAD] Speech END at {end}ms")
                await ten_env.send_cmd(Cmd.create("end_of_sentence"))
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
        # Skip processing if model is not loaded yet
        if self.model is None:
            return

        frame_buf = audio_frame.get_buf()
        self._dump_audio_if_needed(frame_buf, "in")

        # AGC + NS processing (before VAD)
        if self.audio_processor is not None:
            processed = self.audio_processor.process_stream(frame_buf)
            frame_buf = processed

        # Debug: log frame count every 100 frames
        if not hasattr(self, "_frame_count"):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 100 == 0:
            ten_env.log_debug(
                f"[VAD] Frame #{self._frame_count}: {len(frame_buf)} bytes"
            )

        # Maintain pre-buffer during silence (for speech start recovery)
        if not self.is_speech_active:
            self.pre_buffer.extend(frame_buf)
            if len(self.pre_buffer) > self.pre_buffer_bytes:
                self.pre_buffer = self.pre_buffer[-self.pre_buffer_bytes :]

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
        chunk_bytes = self.chunk_samples * BYTES_PER_SAMPLE
        if len(self.audio_buffer) < chunk_bytes:
            return

        # Extract chunk
        audio_buf = bytes(self.audio_buffer[:chunk_bytes])
        self.audio_buffer = self.audio_buffer[chunk_bytes:]

        # Convert int16 PCM to float32 normalized to [-1, 1]
        audio_int16 = np.frombuffer(audio_buf, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Process with FSMN VAD
        res = self.model.generate(
            input=audio_float32,
            cache=self.vad_cache,
            is_final=False,
            chunk_size=self.config.chunk_size_ms,
            speech_noise_thres=0.7,  # 语音/噪声概率阈值,
            is_streaming_input=True,
            detect_mode=0,
        )

        # res format: [{"value": [[beg, end], ...]}]
        if res and len(res) > 0 and res[0]["value"]:
            segments = res[0]["value"]
            ten_env.log_info(f"[VAD] Result: {segments}")
            await self._process_vad_result(ten_env, segments)
