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
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Cmd,
    CmdResult,
    StatusCode,
    AudioFrame,
    AudioFrameDataFmt,
)


class ExtensionTesterBasic(AsyncExtensionTester):
    def __init__(self, input_pcm_file: str):
        super().__init__()
        self.input_pcm_file = input_pcm_file

        self.next_expect_cmd: str = "start_of_sentence"
        self.start_count = 0
        self.end_count = 0
        self.chunks_sent = 0

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        assert os.path.isfile(
            self.input_pcm_file
        ), f"{self.input_pcm_file} is not a valid file"

        ten_env.log_info(f"test_basic: Starting to read audio file {self.input_pcm_file}")

        chunk_size = 160 * 2  # 10ms
        async with aiofiles.open(self.input_pcm_file, "rb") as audio_file:
            while True:
                chunk = await audio_file.read(chunk_size)
                if not chunk:
                    ten_env.log_info(
                        f"test_basic: Audio file ended, sent {self.chunks_sent} chunks"
                    )
                    break

                self.chunks_sent += 1

                # Log every 50 chunks
                if self.chunks_sent % 50 == 0:
                    ten_env.log_info(f"test_basic: Sent {self.chunks_sent} chunks...")

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

        ten_env.log_info(
            f"test_basic: Audio sending complete. start_count={self.start_count}, end_count={self.end_count}"
        )
        ten_env.log_info("test_basic: Waiting 2 seconds for pending VAD events...")
        await asyncio.sleep(2)
        ten_env.log_info("test_basic: Stopping test")
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info(f"test_basic: Received command: {cmd_name}")

        if cmd_name in ["start_of_sentence", "end_of_sentence"]:
            if cmd_name == "start_of_sentence":
                self.start_count += 1
                ten_env.log_info(f"test_basic: start_of_sentence count={self.start_count}")
            elif cmd_name == "end_of_sentence":
                self.end_count += 1
                ten_env.log_info(f"test_basic: end_of_sentence count={self.end_count}")

            self.next_expect_cmd = (
                "end_of_sentence"
                if self.next_expect_cmd == "start_of_sentence"
                else "start_of_sentence"
            )

        cmd_result = CmdResult.create(StatusCode.OK)
        await ten_env.return_result(cmd_result)


def test_basic():
    print("\n=== test_basic: Starting ===")
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(cur_dir, "16k_en_us_helloworld.pcm")

    if not os.path.isfile(test_file):
        print(f"test_basic: Test file {test_file} not found, skipping")
        return

    file_size = os.path.getsize(test_file)
    print(f"test_basic: Test file size: {file_size} bytes")

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

    tester = ExtensionTesterBasic(test_file)
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_basic: Running tester...")
    tester.run()
    print("=== test_basic: Completed ===\n")
