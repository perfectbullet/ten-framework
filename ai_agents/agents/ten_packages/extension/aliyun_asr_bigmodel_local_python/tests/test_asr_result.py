import asyncio
import os
import pytest
from typing_extensions import override
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Data,
    AudioFrame,
    TenError,
    TenErrorCode,
)
import json


class FunASRExtensionTester(AsyncExtensionTester):

    def __init__(self, audio_file_path: str):
        super().__init__()
        self.sender_task: asyncio.Task[None] | None = None
        self.audio_file_path: str = audio_file_path

    async def audio_sender(self, ten_env: AsyncTenEnvTester):
        # 等待连接建立（扩展的 on_start 需要 ~1.5 秒建立连接）
        # 使用更长的延迟确保连接完全建立
        await asyncio.sleep(3)
        print(f"audio_file_path: {self.audio_file_path}")
        with open(self.audio_file_path, "rb") as audio_file:
            chunk_size = 23040
            while True:
                chunk = audio_file.read(chunk_size)
                if not chunk:
                    break
                audio_frame = AudioFrame.create("pcm_frame")
                audio_frame.set_property_int("stream_id", 123)
                audio_frame.set_property_string("remote_user_id", "123")
                audio_frame.alloc_buf(len(chunk))
                buf = audio_frame.lock_buf()
                buf[:] = chunk
                audio_frame.unlock_buf(buf)
                _ = await ten_env.send_audio_frame(audio_frame)
                # 计算实时发送延迟：chunk_size(23040) / (sample_rate(16000) * 2) = 0.72秒
                # 使用稍微快一点的延迟（0.05秒）来加快测试，但不要太快
                await asyncio.sleep(0.1)
        # 音频发送完成，发送结束标记
        print("Audio sending completed, sending end marker...")
        end_data = Data.create("end_of_audio")
        _ = await ten_env.send_data(end_data)

    @override
    async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
        ten_env_tester.log_info("on_start")
        self.sender_task = asyncio.create_task(
            self.audio_sender(ten_env_tester)
        )

    def stop_test_if_checking_failed(
        self,
        ten_env_tester: AsyncTenEnvTester,
        success: bool,
        error_message: str,
    ) -> None:
        if not success:
            err = TenError.create(
                error_code=TenErrorCode.ErrorCodeGeneric,
                error_message=error_message,
            )
            ten_env_tester.stop_test(err)

    @override
    async def on_data(
        self, ten_env_tester: AsyncTenEnvTester, data: Data
    ) -> None:
        data_name = data.get_name()
        if data_name == "asr_result":
            # Check the data structure.
            data_json, _ = data.get_property_to_json()
            data_dict = json.loads(data_json)

            # Print ASR result to console for visibility
            print("\n========== ASR Result ==========")
            print(f"Text: {data_dict.get('text', '')}")
            print(f"Final: {data_dict.get('final', False)}")
            print(f"Start: {data_dict.get('start_ms', 0)} ms")
            print(f"Duration: {data_dict.get('duration_ms', 0)} ms")
            print(f"Language: {data_dict.get('language', '')}")
            print("================================\n")

            ten_env_tester.log_info(f"ASR result: {data_dict}")

            self.stop_test_if_checking_failed(
                ten_env_tester,
                "text" in data_dict,
                f"text is not in data_dict: {data_dict}",
            )

            self.stop_test_if_checking_failed(
                ten_env_tester,
                "final" in data_dict,
                f"final is not in data_dict: {data_dict}",
            )

            if data_dict.get("final") == True:
                ten_env_tester.stop_test()

    @override
    async def on_stop(self, ten_env_tester: AsyncTenEnvTester) -> None:
        if self.sender_task:
            _ = self.sender_task.cancel()
            try:
                await self.sender_task
            except asyncio.CancelledError:
                pass


# Note: This test requires FunASR server (192.168.8.233:10095) to be running


def test_asr_result():
    # FunASR configuration
    property_json = {
        "params": {
            "asr_backend": "funasr",
            "funasr_host": "192.168.8.233",
            "funasr_port": "10095",
            "funasr_is_ssl": False,
            "funasr_chunk_size": "5,10,5",
            "funasr_chunk_interval": 10,
            "funasr_mode": "2pass",
            "funasr_hotwords": "",
            "funasr_itn": True,
            "language_hints": ["zh"],
            "sample_rate": 16000,
        }
    }

    # Use audio file from extension root
    audio_file_path = "/home/zj/Fun-ASR/audio_data_for_test/vad_speech_1_20260408_074440_600000ms.wav"
    # audio_file_path = ""
    print('audio_file_path is ', audio_file_path)
    if not os.path.exists(audio_file_path):
        audio_file_path = os.path.join(
            os.path.dirname(__file__), "..", "zj-1.wav"
        )

    # Check if the audio file exists
    if not os.path.exists(audio_file_path):
        pytest.skip(f"Audio file {audio_file_path} does not exist")

    tester = FunASRExtensionTester(audio_file_path)
    tester.set_test_mode_single(
        "aliyun_asr_bigmodel_local_python", json.dumps(property_json)
    )
    err = tester.run()
    assert err is None, f"err: {err}"
