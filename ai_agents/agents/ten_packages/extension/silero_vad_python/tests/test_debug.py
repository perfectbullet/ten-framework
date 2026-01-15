#
# Debug test to find the difference between smoke and audio tests
#
import json
import os
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
)


class ExtensionTesterDebug1(AsyncExtensionTester):
    """Like smoke test but with os import."""

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info("test_debug1: Starting (with os import)")
        ten_env.log_info(f"test_debug1: Current dir: {os.getcwd()}")
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd) -> None:
        pass


class ExtensionTesterDebug2(AsyncExtensionTester):
    """Like smoke test but with __init__ parameter."""

    def __init__(self, test_value: str = "default"):
        super().__init__()
        self.test_value = test_value

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info(f"test_debug2: Starting with value={self.test_value}")
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd) -> None:
        pass


class ExtensionTesterDebug3(AsyncExtensionTester):
    """Like audio test but without file operations."""

    def __init__(self, test_file: str = "dummy"):
        super().__init__()
        self.test_file = test_file

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info(f"test_debug3: Starting with test_file={self.test_file}")
        # Don't actually open the file
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd) -> None:
        pass


def test_debug1_with_os_import():
    """Test 1: Add os import like audio test."""
    print("\n=== test_debug1: os import test ===")
    property_json = {"use_onnx": True, "sampling_rate": 16000, "threshold": 0.5,
                     "min_speech_duration_ms": 250, "min_silence_duration_ms": 100}
    tester = ExtensionTesterDebug1()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()
    print("=== test_debug1: PASS ===\n")


def test_debug2_with_init_param():
    """Test 2: Add __init__ parameter like audio test."""
    print("\n=== test_debug2: __init__ param test ===")
    property_json = {"use_onnx": True, "sampling_rate": 16000, "threshold": 0.5,
                     "min_speech_duration_ms": 250, "min_silence_duration_ms": 100}
    tester = ExtensionTesterDebug2("test_value")
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()
    print("=== test_debug2: PASS ===\n")


def test_debug3_with_file_param():
    """Test 3: Like audio test but no file operations."""
    print("\n=== test_debug3: file param test ===")
    property_json = {"use_onnx": True, "sampling_rate": 16000, "threshold": 0.5,
                     "min_speech_duration_ms": 250, "min_silence_duration_ms": 100}
    tester = ExtensionTesterDebug3("/path/to/file.pcm")
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    tester.run()
    print("=== test_debug3: PASS ===\n")
