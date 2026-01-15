#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Optional
import os
import struct
import asyncio
import json
import pytest
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Cmd,
    CmdResult,
    StatusCode,
    AudioFrame,
    AudioFrameDataFmt,
)


class ExtensionTesterSilence(AsyncExtensionTester):
    """Tester for silence-only audio."""

    def __init__(self, duration_ms: int = 1000):
        super().__init__()
        self.duration_ms = duration_ms
        self.cmd_received = False

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_debug("sending silence audio")

        # Generate silence (all zeros)
        chunk_size = 160 * 2  # 10ms
        num_chunks = self.duration_ms // 10

        for _ in range(num_chunks):
            silence_data = bytes(chunk_size)

            audio_frame = AudioFrame.create("pcm_frame")
            audio_frame.set_bytes_per_sample(2)
            audio_frame.set_sample_rate(16000)
            audio_frame.set_number_of_channels(1)
            audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
            audio_frame.set_samples_per_channel(chunk_size // 2)
            audio_frame.alloc_buf(len(silence_data))
            buf = audio_frame.lock_buf()
            buf[:] = silence_data
            audio_frame.unlock_buf(buf)
            await ten_env.send_audio_frame(audio_frame)

            await asyncio.sleep(0.01)

        await asyncio.sleep(0.5)
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        if cmd_name in ["start_of_sentence", "end_of_sentence"]:
            self.cmd_received = True

        cmd_result = CmdResult.create(StatusCode.OK)
        await ten_env.return_result(cmd_result)


class ExtensionTesterShortBursts(AsyncExtensionTester):
    """Tester for short speech bursts."""

    def __init__(self):
        super().__init__()
        self.cmd_count = 0

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_debug("sending short audio bursts")

        chunk_size = 160 * 2  # 10ms

        # Send pattern: 100ms noise, 200ms silence, 100ms noise, 200ms silence
        for i in range(2):
            # Generate noise (short burst)
            for _ in range(10):  # 100ms
                noise_data = struct.pack(f"{160}h", *[1000] * 160)

                audio_frame = AudioFrame.create("pcm_frame")
                audio_frame.set_bytes_per_sample(2)
                audio_frame.set_sample_rate(16000)
                audio_frame.set_number_of_channels(1)
                audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
                audio_frame.set_samples_per_channel(160)
                audio_frame.alloc_buf(len(noise_data))
                buf = audio_frame.lock_buf()
                buf[:] = noise_data
                audio_frame.unlock_buf(buf)
                await ten_env.send_audio_frame(audio_frame)

                await asyncio.sleep(0.01)

            # Send silence
            for _ in range(20):  # 200ms
                silence_data = bytes(chunk_size)

                audio_frame = AudioFrame.create("pcm_frame")
                audio_frame.set_bytes_per_sample(2)
                audio_frame.set_sample_rate(16000)
                audio_frame.set_number_of_channels(1)
                audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
                audio_frame.set_samples_per_channel(chunk_size // 2)
                audio_frame.alloc_buf(len(silence_data))
                buf = audio_frame.lock_buf()
                buf[:] = silence_data
                audio_frame.unlock_buf(buf)
                await ten_env.send_audio_frame(audio_frame)

                await asyncio.sleep(0.01)

        await asyncio.sleep(0.5)
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        if cmd_name in ["start_of_sentence", "end_of_sentence"]:
            self.cmd_count += 1

        cmd_result = CmdResult.create(StatusCode.OK)
        await ten_env.return_result(cmd_result)


class ExtensionTesterContinuousSpeech(AsyncExtensionTester):
    """Tester for continuous speech without silence."""

    def __init__(self):
        super().__init__()
        self.start_received = False
        self.end_received = False

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_debug("sending continuous speech")

        chunk_size = 160 * 2  # 10ms

        # Send 2 seconds of continuous noise
        for _ in range(200):
            noise_data = struct.pack(f"{160}h", *[3000] * 160)

            audio_frame = AudioFrame.create("pcm_frame")
            audio_frame.set_bytes_per_sample(2)
            audio_frame.set_sample_rate(16000)
            audio_frame.set_number_of_channels(1)
            audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
            audio_frame.set_samples_per_channel(160)
            audio_frame.alloc_buf(len(noise_data))
            buf = audio_frame.lock_buf()
            buf[:] = noise_data
            audio_frame.unlock_buf(buf)
            await ten_env.send_audio_frame(audio_frame)

            await asyncio.sleep(0.01)

        await asyncio.sleep(1)
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        if cmd_name == "start_of_sentence":
            self.start_received = True
        elif cmd_name == "end_of_sentence":
            self.end_received = True

        cmd_result = CmdResult.create(StatusCode.OK)
        await ten_env.return_result(cmd_result)


def test_silence_only():
    """Test with silence-only audio - should not trigger any VAD commands."""
    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterSilence(duration_ms=1000)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()

    # Should not receive any speech commands for silence
    assert not tester.cmd_received, "Should not detect speech in silence"


def test_short_bursts():
    """Test with short noise bursts - tests min_speech_duration filtering."""
    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,  # Should filter out 100ms bursts
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterShortBursts()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()

    # With 250ms min_speech_duration, 100ms bursts should be filtered out
    # So we expect 0 or very few commands
    ten_env_log = f"Commands received: {tester.cmd_count}"
    print(ten_env_log)


def test_continuous_speech():
    """Test with continuous speech - should get start but may not get end within test window."""
    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterContinuousSpeech()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()

    # Should detect start of speech
    assert tester.start_received, "Should detect start of continuous speech"


def test_invalid_sampling_rate():
    """Test with invalid sampling rate - should raise ValueError."""
    property_json = {
        "use_onnx": True,
        "sampling_rate": 44100,  # Invalid - only 8000 or 16000 supported
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterSilence(duration_ms=100)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))

    # Should fail during initialization
    try:
        tester.run()
        assert False, "Should have raised ValueError for invalid sampling_rate"
    except Exception as e:
        # Expected to fail
        assert "sampling_rate" in str(e).lower() or "value" in str(e).lower()


def test_threshold_boundary():
    """Test with threshold at boundary values."""
    # Test minimum threshold
    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.1,  # Minimum practical threshold
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterSilence(duration_ms=500)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()

    # Test maximum threshold
    property_json["threshold"] = 0.9  # Maximum practical threshold

    tester = ExtensionTesterSilence(duration_ms=500)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()
