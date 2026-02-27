#!/usr/bin/env python3
"""
Test script for local CosyVoice WebSocket TTS service
"""
import asyncio
import sys
from datetime import datetime
from local_speech_synthesizer import (
    LocalSpeechSynthesizer,
    ResultCallback,
    AudioFormat,
)


class TestCallback(ResultCallback):
    """Test callback to collect audio data"""

    def __init__(self):
        self.audio_chunks = []
        self.is_complete = False
        self.error_message = None
        self.first_chunk_time = None
        self.start_time = None

    def on_open(self):
        print("✓ WebSocket connection opened")
        self.start_time = datetime.now()

    def on_complete(self):
        print("✓ TTS synthesis completed")
        self.is_complete = True

    def on_error(self, message):
        print(f"✗ Error occurred: {message}")
        self.error_message = message
        self.is_complete = True

    def on_close(self):
        print("✓ WebSocket connection closed")

    def on_event(self, message):
        print(f"ℹ Event received: {message}")

    def on_data(self, data: bytes):
        if self.first_chunk_time is None:
            self.first_chunk_time = datetime.now()
            ttfb = (
                self.first_chunk_time - self.start_time
            ).total_seconds() * 1000
            print(
                f"✓ First audio chunk received (TTFB: {ttfb:.2f}ms, size: {len(data)} bytes)"
            )
        else:
            print(f"✓ Audio chunk received (size: {len(data)} bytes)")
        self.audio_chunks.append(data)


async def test_local_service():
    """Test the local CosyVoice service"""

    print("=" * 60)
    print("Testing Local CosyVoice WebSocket TTS Service")
    print("=" * 60)

    # Test configuration
    service_url = "ws://192.168.8.233:50002/streaming/ws"
    test_text = '''圆锥曲线主要包括以下三种形式：
1. **椭圆**：它是平面内与两个定点（焦点）的距离之和等于常数的所有点的轨迹，这个常数大于两焦点之间的距离。
2. **抛物线**：它由平面内一条直线（准线）和一个不在直线上且不在同一平面内的点（焦点）共同确定，定义为到焦点的距离与到准线的距离相等的点的集合。
3. **双曲线**：它是平面内与两个定点（焦点）的距离之差的绝对值等于常数的所有点的轨迹，这个常数小于两焦点之间的距离。
这些曲线可以通过将圆锥沿不同方向切割得到。希望这能帮助你更好地理解圆锥曲线的相关知识。'''
    speaker_id = "hutao"  # Change to your available speaker

    print("\nConfiguration:")
    print(f"  Service URL: {service_url}")
    print(f"  Speaker ID: {speaker_id}")
    print(f"  Test Text: {test_text}")
    print()

    # Create callback
    callback = TestCallback()

    # Create synthesizer
    print("Creating synthesizer...")
    synthesizer = LocalSpeechSynthesizer(
        model="cosyvoice",  # Model name (not used by local service)
        voice=speaker_id,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        callback=callback,
        url=service_url,
    )

    try:
        # Start synthesis
        print("\nSending synthesis request...")
        start_time = datetime.now()
        synthesizer.streaming_call(test_text)

        # Wait for completion (timeout: 30 seconds)
        timeout = 30
        for i in range(timeout * 10):
            if callback.is_complete:
                break
            await asyncio.sleep(0.1)
        else:
            print(f"\n✗ Timeout waiting for completion after {timeout}s")
            return False

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        # Check results
        print(f"\n{'=' * 60}")
        print("Test Results:")
        print(f"{'=' * 60}")

        if callback.error_message:
            print(f"✗ Test FAILED with error: {callback.error_message}")
            return False

        total_audio_bytes = sum(len(chunk) for chunk in callback.audio_chunks)

        # Calculate audio duration (16kHz, 16-bit mono PCM)
        sample_rate = 16000
        bytes_per_sample = 2
        audio_duration = total_audio_bytes / (sample_rate * bytes_per_sample)

        # Calculate RTF (Real Time Factor)
        rtf = total_time / audio_duration if audio_duration > 0 else 0

        print("✓ Test PASSED")
        print("\nStatistics:")
        print(f"  Audio chunks received: {len(callback.audio_chunks)}")
        print(f"  Total audio bytes: {total_audio_bytes}")
        print(f"  Audio duration: {audio_duration:.2f}s")
        print(f"  Total time: {total_time:.2f}s")
        print(
            f"  RTF: {rtf:.3f} {'(real-time)' if rtf < 1.0 else '(slower than real-time)'}"
        )

        if callback.first_chunk_time:
            ttfb = (
                callback.first_chunk_time - start_time
            ).total_seconds() * 1000
            print(f"  TTFB: {ttfb:.2f}ms")

        # Optionally save audio to file
        save_audio = input("\nSave audio to file? (y/n): ").strip().lower()
        if save_audio == "y":
            import wave

            output_file = "test_output.wav"
            with wave.open(output_file, "wb") as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)  # 16kHz
                wf.writeframes(b"".join(callback.audio_chunks))
            print(f"✓ Audio saved to {output_file}")

        return True

    except Exception as e:
        print(f"\n✗ Test FAILED with exception: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Close synthesizer
        print("\nClosing synthesizer...")
        synthesizer.close()
        print("✓ Test completed\n")


def main():
    """Main entry point"""
    try:
        result = asyncio.run(test_local_service())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
