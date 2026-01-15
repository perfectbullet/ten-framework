#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
Smoke test to verify Silero VAD extension can be initialized.
This test doesn't send any audio, just checks if the extension starts without errors.
"""
import json
from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
)


class ExtensionTesterSmoke(AsyncExtensionTester):
    """Minimal tester that just starts and stops."""

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info("test_smoke: Extension started successfully!")
        ten_env.log_info("test_smoke: Stopping test now")
        ten_env.stop_test()

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd) -> None:
        pass


def test_smoke_onnx():
    """Test that extension can initialize with ONNX model."""
    print("\n=== test_smoke_onnx: Starting ===")
    print("test_smoke_onnx: This test verifies extension initialization only")

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

    tester = ExtensionTesterSmoke()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_smoke_onnx: Running tester...")
    tester.run()
    print("=== test_smoke_onnx: Completed ===\n")


def test_smoke_jit():
    """Test that extension can initialize with JIT model."""
    print("\n=== test_smoke_jit: Starting ===")
    print("test_smoke_jit: This test verifies extension initialization only")

    property_json = {
        "use_onnx": False,  # Use JIT model
        "sampling_rate": 16000,
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 100,
        "speech_pad_ms": 30,
        "chunk_size": 512,
        "dump": False,
        "dump_path": "",
    }

    tester = ExtensionTesterSmoke()
    tester.set_test_mode_single("silero_vad_python", json.dumps(property_json))
    print("test_smoke_jit: Running tester...")
    tester.run()
    print("=== test_smoke_jit: Completed ===\n")
