#!/usr/bin/env python3
"""
Test script for local CosyVoice WebSocket TTS service.
Tests streaming text input to simulate real LLM output behavior.

Test data lives in test_data/*.json — just add a JSON file to add a test.
"""

import asyncio
import json
import os
import sys
import wave
from datetime import datetime
from pathlib import Path

from local_speech_synthesizer import (
    LocalSpeechSynthesizer,
    ResultCallback,
    AudioFormat,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_DATA_DIR = SCRIPT_DIR / "test_data"

SERVICE_URL = "ws://192.168.8.233:50002/streaming/ws"
SPEAKER_ID = "Nilou"
CHUNK_DELAY = 0.1  # seconds between chunks


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


class TestCallback(ResultCallback):
    def __init__(self):
        self.audio_chunks: list[bytes] = []
        self.is_complete = False
        self.error_message: str | None = None
        self.first_chunk_time: datetime | None = None
        self.start_time: datetime | None = None
        self.completion_count = 0
        self.expected_completions = 1

    def on_open(self):
        print("  [callback] WebSocket connection opened")
        self.start_time = datetime.now()

    def on_complete(self):
        self.completion_count += 1
        print(
            f"  [callback] TTS synthesis completed "
            f"({self.completion_count}/{self.expected_completions})"
        )
        if self.completion_count >= self.expected_completions:
            self.is_complete = True

    def on_error(self, message):
        print(f"  [callback] Error: {message}")
        self.error_message = message
        self.is_complete = True

    def on_close(self):
        print("  [callback] WebSocket connection closed")

    def on_event(self, message):
        print(f"  [callback] Event: {message}")

    def on_data(self, data: bytes):
        if self.first_chunk_time is None:
            self.first_chunk_time = datetime.now()
            ttfb = (
                (self.first_chunk_time - self.start_time).total_seconds() * 1000
            )
            print(
                f"  [callback] First audio chunk "
                f"(TTFB: {ttfb:.2f}ms, size: {len(data)} bytes)"
            )
        self.audio_chunks.append(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_for_completion(callback: TestCallback, timeout: int = 300):
    for _ in range(timeout * 10):
        if callback.is_complete:
            return True
        await asyncio.sleep(0.1)
    print(f"  Timeout waiting for completion after {timeout}s")
    return False


def _print_stats(callback: TestCallback, start_time: datetime, label: str):
    total_audio_bytes = sum(len(c) for c in callback.audio_chunks)
    audio_duration = total_audio_bytes / 32000  # 16kHz * 2 bytes
    total_time = (datetime.now() - start_time).total_seconds()
    rtf = total_time / audio_duration if audio_duration > 0 else 0

    print(f"\n  [{label}] Statistics:")
    print(f"    Audio chunks: {len(callback.audio_chunks)}")
    print(f"    Total audio bytes: {total_audio_bytes}")
    print(f"    Audio duration: {audio_duration:.2f}s")
    print(f"    Total time: {total_time:.2f}s")
    print(
        f"    RTF: {rtf:.3f} "
        f"{'(real-time)' if rtf < 1.0 else '(slower than real-time)'}"
    )
    if callback.first_chunk_time and callback.start_time:
        ttfb = (
            (callback.first_chunk_time - callback.start_time).total_seconds()
            * 1000
        )
        print(f"    TTFB: {ttfb:.2f}ms")


def _save_audio(callback: TestCallback, filepath: Path):
    if not callback.audio_chunks:
        print(f"  No audio data to save for {filepath}")
        return
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"".join(callback.audio_chunks))
    print(f"  Audio saved to {filepath}")


# ---------------------------------------------------------------------------
# Core test runner
# ---------------------------------------------------------------------------


async def run_test(name: str, chunks: list[dict]):
    """Run a single TTS test with the given chunks.

    Args:
        name: test name (used for display and output file naming)
        chunks: list of {"text": str, "text_input_end": bool}
    """
    wav_path = TEST_DATA_DIR / f"{name}.wav"

    print("\n" + "=" * 60)
    print(f"Test: {name}  ({len(chunks)} chunks)")
    print("=" * 60)

    callback = TestCallback()
    synthesizer = LocalSpeechSynthesizer(
        model="cosyvoice",
        voice=SPEAKER_ID,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        callback=callback,
        url=SERVICE_URL,
    )

    try:
        start_time = datetime.now()

        non_empty_count = sum(1 for c in chunks if c["text"].strip())
        callback.expected_completions = non_empty_count
        print(f"  Expected completions: {non_empty_count}")

        for i, chunk in enumerate(chunks):
            text = chunk["text"]
            text_input_end = chunk["text_input_end"]
            print(
                f'  [{i + 1}/{len(chunks)}] Sending: "{text}" '
                f"(end={text_input_end})"
            )

            if text.strip():
                synthesizer.streaming_call(text)

            if text_input_end:
                print("  Signaling text input end")
                break

            await asyncio.sleep(CHUNK_DELAY)

        print("\n  Waiting for TTS completion...")
        await _wait_for_completion(callback, timeout=300)
        _print_stats(callback, start_time, name)
        _save_audio(callback, wav_path)

        return callback.error_message is None

    except Exception as e:
        print(f"  Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        synthesizer.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def discover_tests() -> list[Path]:
    """Find all JSON files in test_data/ sorted by name."""
    if not TEST_DATA_DIR.is_dir():
        print(f"Test data directory not found: {TEST_DATA_DIR}")
        return []
    return sorted(TEST_DATA_DIR.glob("*.json"))


async def run_all_tests():
    print("=" * 60)
    print("Testing Local CosyVoice WebSocket TTS Service")
    print(f"Test data dir: {TEST_DATA_DIR}")
    print("=" * 60)

    json_files = discover_tests()
    if not json_files:
        print("No test JSON files found.")
        return False

    print(f"Found {len(json_files)} test(s): "
          + ", ".join(f.stem for f in json_files))

    results: dict[str, bool] = {}
    for jf in json_files:
        chunks = json.loads(jf.read_text(encoding="utf-8"))
        results[jf.stem] = await run_test(jf.stem, chunks)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    for name, passed in results.items():
        print(f"  {name}: {'PASSED' if passed else 'FAILED'}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed


def main():
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
