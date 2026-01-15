#
# Test to verify the difference in behavior
#
import json
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
)


class ExtensionTesterTiming(AsyncExtensionTester):
    """Test that calls stop_test immediately."""

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info("test_timing: Starting")
        ten_env.log_info("test_timing: Calling stop_test immediately")
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd) -> None:
        pass


def test_immediate_stop():
    """Test with immediate stop_test call."""
    print("\n=== test_immediate_stop: Starting ===")
    property_json = {"use_onnx": True, "sampling_rate": 16000, "threshold": 0.5,
                     "min_speech_duration_ms": 250, "min_silence_duration_ms": 100}
    tester = ExtensionTesterTiming()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_immediate_stop: Running tester...")
    tester.run()
    print("=== test_immediate_stop: Done ===\n")
