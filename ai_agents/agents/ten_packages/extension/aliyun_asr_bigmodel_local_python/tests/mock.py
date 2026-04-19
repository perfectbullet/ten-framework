#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
Mock fixtures for testing AliyunASRBigmodelExtension without requiring
a real FunASR server connection.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(scope="function")
def patch_funasr_recognition():
    """
    Mock FunASRRecognition class for isolated testing.

    This fixture intercepts the FunASRRecognition class instantiation
    and provides a mock object that can simulate all recognition events
    without requiring a real WebSocket connection to FunASR server.
    """
    patch_target = "ten_packages.extension.aliyun_asr_bigmodel_local_python.extension.FunASRRecognition"

    # Store the latest instance for test access
    instances = []

    # Create a custom class to capture callback
    class MockFunASRRecognition:
        def __init__(self, *args, callback=None, **kwargs):
            self._stored_callback = callback
            self._is_running_state = True
            instances.append(self)

        def start(self, **kwargs):
            pass

        def send_audio_frame(self, audio_data):
            pass

        def send_end_of_speech(self):
            pass

        def stop(self, timeout=2.0):
            self._is_running_state = False

        def is_running(self):
            return self._is_running_state

        async def trigger_open(self):
            if self._stored_callback:
                await self._stored_callback.on_open()

        async def trigger_result(self, text="test", is_final=False, start_ms=0, duration_ms=100):
            if self._stored_callback:
                from ten_packages.extension.aliyun_asr_bigmodel_local_python.funasr_adapter import FunASRRecognitionResult

                result_dict = {
                    "text": text,
                    "is_final": is_final,
                    "mode": "2pass-offline" if is_final else "2pass-online",
                    "wav_name": "test",
                }
                if is_final:
                    result_dict["stamp_sents"] = [{
                        "start": start_ms,
                        "end": start_ms + duration_ms,
                        "text_seg": "",
                        "ts_list": []
                    }]

                result = FunASRRecognitionResult(result_dict)
                await self._stored_callback.on_event(result)

        async def trigger_close(self):
            self._is_running_state = False
            if self._stored_callback:
                await self._stored_callback.on_close()

        async def trigger_error(self, message="Test error"):
            if self._stored_callback:
                from ten_packages.extension.aliyun_asr_bigmodel_local_python.funasr_adapter import FunASRRecognitionResult

                result = FunASRRecognitionResult({
                    "text": "",
                    "error": message,
                    "is_final": False
                })
                result.status_code = 500
                result.message = message
                await self._stored_callback.on_error(result)

    with patch(patch_target, MockFunASRRecognition):
        yield SimpleNamespace(
            recognition_class=MockFunASRRecognition,
            get_instance=lambda: instances[-1] if instances else None
        )
