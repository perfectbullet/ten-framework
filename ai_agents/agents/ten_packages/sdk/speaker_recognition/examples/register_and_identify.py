#!/usr/bin/env python3
"""
Batch enrollment and identification example.

This example demonstrates:
1. Registering multiple speakers from a directory
2. Identifying audio against all registered speakers
3. Performance testing
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from speaker_recognition import SpeakerRecognitionClient


def register_speakers_from_directory(
    client: SpeakerRecognitionClient, audio_dir: Path, name_mapping: dict
):
    """
    Register multiple speakers from a directory.

    Args:
        client: Speaker recognition client
        audio_dir: Directory containing audio files
        name_mapping: Mapping from filename pattern to speaker name
    """
    print(f"\n=== Registering Speakers from {audio_dir} ===")

    audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.mp3"))

    if not audio_files:
        print("No audio files found!")
        return []

    registered = []

    for audio_file in audio_files:
        # Get speaker name from mapping or use filename
        speaker_name = name_mapping.get(
            audio_file.stem, audio_file.stem
        )

        try:
            result = client.register_speaker(
                audio_path=str(audio_file),
                speaker_name=speaker_name,
            )
            registered.append(result)
            print(f"✓ Registered: {speaker_name} ({result.speaker_id})")

        except Exception as e:
            print(f"✗ Failed to register {audio_file.name}: {e}")

    print(f"\nRegistered {len(registered)} speakers")
    return registered


def identify_audio_files(
    client: SpeakerRecognitionClient, audio_dir: Path
):
    """
    Identify audio files against registered speakers.

    Args:
        client: Speaker recognition client
        audio_dir: Directory containing test audio files
    """
    print(f"\n=== Identifying Audio Files from {audio_dir} ===")

    audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.mp3"))

    if not audio_files:
        print("No audio files found!")
        return

    results = []

    for audio_file in audio_files:
        start_time = time.time()
        result = client.identify_speaker(str(audio_file))
        elapsed = time.time() - start_time

        results.append((audio_file.name, result, elapsed))

        status = "✓" if result.matched else "✗"
        print(
            f"{status} {audio_file.name}: "
            f"{result.speaker_name if result.matched else 'Unknown'} "
            f"(similarity: {result.similarity:.4f}, time: {elapsed*1000:.1f}ms)"
        )

    # Summary
    matched = sum(1 for _, r, _ in results if r.matched)
    avg_time = sum(elapsed for _, _, elapsed in results) / len(results) * 1000

    print(f"\nSummary:")
    print(f"  Total: {len(results)}")
    print(f"  Matched: {matched}")
    print(f"  Unknown: {len(results) - matched}")
    print(f"  Avg identification time: {avg_time:.1f}ms")


def run_performance_test(client: SpeakerRecognitionClient, test_audio: str):
    """
    Run performance benchmark.

    Args:
        client: Speaker recognition client
        test_audio: Path to test audio file
    """
    print("\n=== Performance Test ===")

    # Warmup
    client.identify_speaker(test_audio)

    # Benchmark
    iterations = 10
    times = []

    print(f"Running {iterations} iterations...")

    for i in range(iterations):
        start = time.time()
        client.identify_speaker(test_audio)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"  Iteration {i+1}: {elapsed*1000:.1f}ms")

    avg_time = sum(times) / len(times) * 1000
    min_time = min(times) * 1000
    max_time = max(times) * 1000

    print(f"\nResults:")
    print(f"  Average: {avg_time:.1f}ms")
    print(f"  Min: {min_time:.1f}ms")
    print(f"  Max: {max_time:.1f}ms")


def main():
    """Run batch enrollment and identification example."""

    # Configuration
    enrollment_dir = Path("audio/enrollment")  # Change to your enrollment audio directory
    test_dir = Path("audio/test")  # Change to your test audio directory

    # Name mapping (filename pattern -> speaker name)
    name_mapping = {
        "person_1": "Alice",
        "person_2": "Bob",
        "person_3": "Charlie",
    }

    print("Speaker Recognition SDK - Batch Example")
    print("=" * 50)

    # Create client
    client = SpeakerRecognitionClient()

    try:
        with client:
            # Check if directories exist
            if not enrollment_dir.exists():
                print(f"\nEnrollment directory not found: {enrollment_dir}")
                print("Please create it and add audio files for enrollment.")

                # Example usage
                print("\nExample directory structure:")
                print("  audio/enrollment/")
                print("    alice.wav")
                print("    bob.wav")
                print("    charlie.wav")
                print("  audio/test/")
                print("    test_alice.wav")
                print("    test_bob.wav")

                return

            # Register speakers
            registered = register_speakers_from_directory(
                client, enrollment_dir, name_mapping
            )

            if not registered:
                return

            # Identify test files
            if test_dir.exists():
                identify_audio_files(client, test_dir)
            else:
                print(f"\nTest directory not found: {test_dir}")

            # Performance test
            if registered:
                # Use first registered speaker's audio for performance test
                print("\nNote: Performance test requires a test audio file path")
                print("You can test with: python examples/register_and_identify.py <test_audio>")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Allow passing test audio as argument
    if len(sys.argv) > 1:
        # Performance test mode
        test_audio = sys.argv[1]
        client = SpeakerRecognitionClient()

        with client:
            run_performance_test(client, test_audio)
    else:
        main()
