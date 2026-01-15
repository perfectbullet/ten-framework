#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Optional
import os
import aiofiles
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


class ExtensionTesterConfig(AsyncExtensionTester):
    def __init__(self, input_pcm_file: str):
        super().__init__()
        self.input_pcm_file = input_pcm_file
        self.cmd_received = False

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        assert os.path.isfile(
            self.input_pcm_file
        ), f"{self.input_pcm_file} is not a valid file"

        ten_env.log_debug(f"start reading audio file {self.input_pcm_file}")

        chunk_size = 160 * 2  # 10ms
        async with aiofiles.open(self.input_pcm_file, "rb") as audio_file:
            for _ in range(200):  # Read first 2 seconds
                chunk = await audio_file.read(chunk_size)
                if not chunk:
                    break

                audio_frame = AudioFrame.create("pcm_frame")
                audio_frame.set_bytes_per_sample(2)
                audio_frame.set_sample_rate(16000)
                audio_frame.set_number_of_channels(1)
                audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
                audio_frame.set_samples_per_channel(len(chunk) // 2)
                audio_frame.alloc_buf(len(chunk))
                buf = audio_frame.lock_buf()
                buf[:] = chunk
                audio_frame.unlock_buf(buf)
                await ten_env.send_audio_frame(audio_frame)

                await asyncio.sleep(0.01)

        await asyncio.sleep(1)
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        if cmd_name in ["start_of_sentence", "end_of_sentence"]:
            self.cmd_received = True

        cmd_result = CmdResult.create(StatusCode.OK)
        await ten_env.return_result(cmd_result)


def get_test_file():
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(cur_dir, "16k_en_us_helloworld.pcm")


def test_default_config():
    """Test with default Silero VAD configuration."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

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

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()


def test_low_threshold():
    """Test with low threshold (more sensitive)."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.3,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()


def test_high_threshold():
    """Test with high threshold (less sensitive)."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.7,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()


def test_short_min_speech_duration():
    """Test with shorter minimum speech duration."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 100,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()


def test_long_min_silence_duration():
    """Test with longer minimum silence duration."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()


def test_jit_mode():
    """Test with JIT mode instead of ONNX."""
    test_file = get_test_file()

    if not os.path.isfile(test_file):
        pytest.skip(f"test file {test_file} not found")

    property_json = {
        "use_onnx": False,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterConfig(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()
