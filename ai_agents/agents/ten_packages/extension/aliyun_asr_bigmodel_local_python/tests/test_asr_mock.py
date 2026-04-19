#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
Mock tests for AliyunASRBigmodelExtension.

These tests use mocked FunASRRecognition to verify extension behavior
without requiring a real FunASR server connection.
"""

import asyncio
import json
from typing_extensions import override

import pytest
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    AudioFrame,
    Data,
    TenError,
    TenErrorCode,
)

from .mock import patch_funasr_recognition  # noqa: F401


class FunASRMockExtensionTester(AsyncExtensionTester):
    """Tester for FunASR extension with mock recognition."""

    def __init__(self):
        super().__init__()
        self.sender_task: asyncio.Task[None] | None = None
        self.stopped = False
        self.asr_results: list[dict] = []
        self.error_received: bool = False

    async def audio_sender(self, ten_env: AsyncTenEnvTester, chunks: int = 5):
        """Send simulated audio data."""
        for _ in range(chunks):
            chunk = b"\x01\x02" * 160  # 320 bytes
            audio_frame = AudioFrame.create("pcm_frame")
            audio_frame.set_property_int("stream_id", 123)
            audio_frame.alloc_buf(len(chunk))
            buf = audio_frame.lock_buf()
            buf[:] = chunk
            audio_frame.unlock_buf(buf)
            await ten_env.send_audio_frame(audio_frame)
            await asyncio.sleep(0.02)

    @override
    async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
        self.sender_task = asyncio.create_task(
            self.audio_sender(ten_env_tester)
        )

    def stop_test_if_failed(
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
            data_json, _ = data.get_property_to_json()
            data_dict = json.loads(data_json)
            self.asr_results.append(data_dict)

            # Check required fields
            self.stop_test_if_failed(
                ten_env_tester,
                "text" in data_dict,
                f"text missing: {data_dict}",
            )
            self.stop_test_if_failed(
                ten_env_tester,
                "final" in data_dict,
                f"final missing: {data_dict}",
            )
            self.stop_test_if_failed(
                ten_env_tester,
                "start_ms" in data_dict,
                f"start_ms missing: {data_dict}",
            )
            self.stop_test_if_failed(
                ten_env_tester,
                "duration_ms" in data_dict,
                f"duration_ms missing: {data_dict}",
            )
            self.stop_test_if_failed(
                ten_env_tester,
                "language" in data_dict,
                f"language missing: {data_dict}",
            )

            if data_dict.get("final") is True:
                ten_env_tester.stop_test()

        elif data_name == "asr_error":
            self.error_received = True
            ten_env_tester.log_info("ASR error received")

    @override
    async def on_stop(self, ten_env_tester: AsyncTenEnvTester) -> None:
        self.stopped = True
        if self.sender_task:
            self.sender_task.cancel()
            try:
                await self.sender_task
            except asyncio.CancelledError:
                pass


def test_asr_result_with_mock(patch_funasr_recognition):
    """Test ASR result handling with mocked FunASR."""

    async def simulate_asr_workflow():
        # Wait for extension to initialize
        await asyncio.sleep(0.3)

        # Get the mock instance
        mock_instance = patch_funasr_recognition.get_instance()
        if mock_instance:
            # Trigger connection opened
            await mock_instance.trigger_open()

            # Wait a bit
            await asyncio.sleep(0.1)

            # Send intermediate result
            await mock_instance.trigger_result(
                text="你好",
                is_final=False,
                start_ms=0,
                duration_ms=500
            )

            await asyncio.sleep(0.1)

            # Send final result
            await mock_instance.trigger_result(
                text="你好世界",
                is_final=True,
                start_ms=0,
                duration_ms=1000
            )

    # Start simulation in background
    asyncio.create_task(simulate_asr_workflow())

    # Minimal required config
    property_json = {
        "params": {
            "sample_rate": 16000,
        }
    }

    tester = FunASRMockExtensionTester()
    tester.set_test_mode_single(
        "aliyun_asr_bigmodel_local_python",
        json.dumps(property_json)
    )
    err = tester.run()
    assert err is None, f"test_asr_result_with_mock failed: {err}"
    assert len(tester.asr_results) >= 1


def test_pause_resume_mechanism(patch_funasr_recognition):
    """Test pause/resume mechanism during ASR processing."""

    async def simulate_pause_resume():
        await asyncio.sleep(0.3)
        mock_instance = patch_funasr_recognition.get_instance()
        if mock_instance:
            await mock_instance.trigger_open()
            await asyncio.sleep(0.2)
            await mock_instance.trigger_result(
                text="暂停恢复测试",
                is_final=True,
                start_ms=0,
                duration_ms=800
            )

    class PauseResumeTester(FunASRMockExtensionTester):
        @override
        async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
            await asyncio.sleep(0.1)
            # Send pause first
            pause_data = Data.create("pause_asr")
            await ten_env_tester.send_data(pause_data)
            await asyncio.sleep(0.1)
            # Then resume
            resume_data = Data.create("resume_asr")
            await ten_env_tester.send_data(resume_data)
            # Start audio sender after resume
            self.sender_task = asyncio.create_task(
                self.audio_sender(ten_env_tester)
            )

    asyncio.create_task(simulate_pause_resume())

    property_json = {
        "params": {
            "sample_rate": 16000,
        }
    }

    tester = PauseResumeTester()
    tester.set_test_mode_single(
        "aliyun_asr_bigmodel_local_python",
        json.dumps(property_json)
    )
    err = tester.run()
    assert err is None, f"test_pause_resume_mechanism failed: {err}"


def test_connection_handling(patch_funasr_recognition):
    """Test connection open/close handling."""

    async def simulate_connection():
        await asyncio.sleep(0.3)
        mock_instance = patch_funasr_recognition.get_instance()
        if mock_instance:
            await mock_instance.trigger_open()
            await asyncio.sleep(0.1)
            await mock_instance.trigger_close()

    asyncio.create_task(simulate_connection())

    property_json = {
        "params": {
            "sample_rate": 16000,
        }
    }

    class ConnectionTester(FunASRMockExtensionTester):
        @override
        async def on_data(self, ten_env_tester: AsyncTenEnvTester, data: Data) -> None:
            # Don't stop on close, let extension handle it
            if data.get_name() == "asr_result":
                ten_env_tester.stop_test()

        @override
        async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
            # Don't send audio, just wait for connection events
            pass

    tester = ConnectionTester()
    tester.set_test_mode_single(
        "aliyun_asr_bigmodel_local_python",
        json.dumps(property_json)
    )
    err = tester.run()
    assert err is None, f"test_connection_handling failed: {err}"


def test_error_handling(patch_funasr_recognition):
    """Test error handling from FunASR."""

    async def simulate_error():
        await asyncio.sleep(0.3)
        mock_instance = patch_funasr_recognition.get_instance()
        if mock_instance:
            await mock_instance.trigger_open()
            await asyncio.sleep(0.1)
            await mock_instance.trigger_error("Connection timeout")

    asyncio.create_task(simulate_error())

    property_json = {
        "params": {
            "sample_rate": 16000,
        }
    }

    class ErrorTester(FunASRMockExtensionTester):
        @override
        async def on_data(self, ten_env_tester: AsyncTenEnvTester, data: Data) -> None:
            if data.get_name() == "asr_error":
                self.error_received = True
                # Error received, stop test
                ten_env_tester.stop_test()

        @override
        async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
            # Don't send audio, just wait for error
            pass

    tester = ErrorTester()
    tester.set_test_mode_single(
        "aliyun_asr_bigmodel_local_python",
        json.dumps(property_json)
    )
    err = tester.run()
    assert err is None, f"test_error_handling failed: {err}"
