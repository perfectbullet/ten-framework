#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
Audio test for Silero VAD extension.
Simpler version that doesn't use aiofiles.
"""
import os
import asyncio
import json
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Cmd,
    CmdResult,
    StatusCode,
    AudioFrame,
    AudioFrameDataFmt,
)


class ExtensionTesterAudio(AsyncExtensionTester):
    def __init__(self, input_pcm_file: str, max_chunks: int = 200):
        super().__init__()
        self.input_pcm_file = input_pcm_file
        self.max_chunks = max_chunks  # Safety limit to prevent hanging

        self.start_count = 0
        self.end_count = 0
        self.chunks_sent = 0

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info(f"test_audio: Starting with audio file {self.input_pcm_file}")

        # Read entire file into memory first
        if not os.path.isfile(self.input_pcm_file):
            ten_env.log_error(f"test_audio: File not found: {self.input_pcm_file}")
            ten_env.stop_test()
            return

        with open(self.input_pcm_file, "rb") as f:
            audio_data = f.read()

        file_size = len(audio_data)
        chunk_size = 160 * 2  # 10ms
        total_chunks = file_size // chunk_size

        ten_env.log_info(f"test_audio: File size={file_size} bytes, chunks={total_chunks}")

        # Limit chunks for testing
        chunks_to_send = min(total_chunks, self.max_chunks)

        for i in range(chunks_to_send):
            start = i * chunk_size
            end = start + chunk_size
            chunk = audio_data[start:end]

            self.chunks_sent += 1

            # Log every 50 chunks
            if self.chunks_sent % 50 == 0:
                ten_env.log_info(f"test_audio: Sent {self.chunks_sent}/{chunks_to_send} chunks")

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

            # Small delay between frames
            await asyncio.sleep(0.005)

        ten_env.log_info(
            f"test_audio: Done sending. start={self.start_count}, end={self.end_count}"
        )
        await asyncio.sleep(0.5)
        ten_env.log_info("test_audio: Stopping test")
        ten_env.stop_test()

    async def on_audio_frame(self, ten_env: AsyncTenEnvTester, audio_frame) -> None:
        # Receive and discard output audio frames from the extension
        # to prevent message queue from filling up
        pass

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info(f"test_audio: Got command: {cmd_name}")

        if cmd_name == "start_of_sentence":
            self.start_count += 1
        elif cmd_name == "end_of_sentence":
            self.end_count += 1

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)


def test_with_audio():
    """Test with actual audio file."""
    print("\n=== test_with_audio: Starting ===")

    cur_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(cur_dir, "16k_en_us_helloworld.pcm")

    if not os.path.isfile(test_file):
        print(f"test_with_audio: Test file not found: {test_file}")
        return

    file_size = os.path.getsize(test_file)
    print(f"test_with_audio: Test file size: {file_size} bytes")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "passthrough": False,  # Disable audio passthrough for testing
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterAudio(test_file, max_chunks=200)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_with_audio: Running tester...")
    tester.run()
    print(f"test_with_audio: start={tester.start_count}, end={tester.end_count}")
    print("=== test_with_audio: Completed ===\n")


def test_with_noise():
    """Test with generated noise (no file needed)."""
    print("\n=== test_with_noise: Starting ===")

    property_json = {
        "use_onnx": True,
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "passthrough": False,  # Disable audio passthrough for testing
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterAudio("", max_chunks=100)  # Will generate noise
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_with_noise: Running tester...")
    tester.run()
    print(f"test_with_noise: start={tester.start_count}, end={tester.end_count}")
    print("=== test_with_noise: Completed ===\n")
