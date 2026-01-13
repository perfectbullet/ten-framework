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

import numpy as np
import os
import asyncio

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

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        config_json, _ = await ten_env.get_property_to_json("")
        self.config = SileroVADConfig.model_validate_json(config_json)
        ten_env.log_debug(f"config: {self.config}")

        # Validate sampling rate
        if self.config.sampling_rate not in (8000, 16000):
            ten_env.log_error(f"Invalid sampling_rate: {self.config.sampling_rate}. Must be 8000 or 16000")
            raise ValueError(f"sampling_rate must be 8000 or 16000, got {self.config.sampling_rate}")

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
            ten_env.log_error("silero-vad is not installed. Install with: pip install silero-vad torch torchaudio")
            raise ImportError("silero-vad package is required")

        ten_env.log_info(f"Loading Silero VAD model (ONNX: {self.config.use_onnx})...")

        try:
            self.model = load_silero_vad(onnx=self.config.use_onnx)
        except Exception as e:
            if self.config.use_onnx:
                ten_env.log_warn(f"Failed to load ONNX model: {e}. Falling back to JIT model...")
                self.model = load_silero_vad(onnx=False)
            else:
                raise

        self.vad_iterator = VADIterator(
            self.model,
            threshold=self.config.threshold,
            sampling_rate=self.config.sampling_rate,
            min_speech_duration_ms=self.config.min_speech_duration_ms,
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
        self.is_speech_active = False
        self.current_start_ms = 0
        self.total_samples_processed = 0
        if self.vad_iterator is not None:
            self.vad_iterator.reset()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd name: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        pass

    async def _send_audio_frame(
        self, ten_env: AsyncTenEnv, audio_data: bytes
    ) -> None:
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

        dump_file = os.path.join(
            self.config.dump_path, f"{self.name}_{suffix}.pcm"
        )
        with open(dump_file, "ab") as f:
            f.write(buf)

    async def _process_vad_result(
        self, ten_env: AsyncTenEnv, result: dict
    ) -> None:
        """Process VAD detection result and send appropriate commands."""

        if 'start' in result:
            # Speech start detected
            if not self.is_speech_active:
                self.is_speech_active = True
                self.current_start_ms = result['start']
                ten_env.log_info(f"Speech start detected at {result['start']}ms")

                # Send start_of_sentence command
                await ten_env.send_cmd(Cmd.create("start_of_sentence"))

        elif 'end' in result:
            # Speech end detected
            if self.is_speech_active:
                self.is_speech_active = False
                duration_ms = result['end'] - self.current_start_ms
                ten_env.log_info(
                    f"Speech end detected at {result['end']}ms "
                    f"(duration: {duration_ms}ms)"
                )

                # Send end_of_sentence command
                await ten_env.send_cmd(Cmd.create("end_of_sentence"))

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        frame_buf = audio_frame.get_buf()
        self._dump_audio_if_needed(frame_buf, "in")

        # Direct passthrough - forward audio unchanged
        await self._send_audio_frame(ten_env, frame_buf)

        # Accumulate audio buffer
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
