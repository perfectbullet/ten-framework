#!/usr/bin/env python3
"""
Basic usage example for Speaker Recognition SDK.

This example demonstrates:
1. Creating a client
2. Registering speakers
3. Identifying a speaker
4. Verifying a speaker
"""

import sys
from pathlib import Path

# Add SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from speaker_recognition import (
    SpeakerRecognitionClient,
    SpeakerIdGenerator,
)


def main():
    """Run basic usage example."""

    # Create client (using default configuration)
    print("Creating Speaker Recognition Client...")
    client = SpeakerRecognitionClient()

    try:
        with client:
            # Example 1: Register a speaker
            print("\n=== Example 1: Register a Speaker ===")
            speaker_name = input("Enter speaker name: ").strip()
            audio_path = input("Enter path to enrollment audio file: ").strip()

            try:
                result = client.register_speaker(
                    audio_path=audio_path,
                    speaker_name=speaker_name,
                )
                print(f"✓ {result}")
                print(f"  Speaker ID: {result.speaker_id}")
                print(f"  Embedding shape: {result.embedding.shape}")

            except Exception as e:
                print(f"✗ Registration failed: {e}")
                return

            # Example 2: Identify a speaker
            print("\n=== Example 2: Identify a Speaker ===")
            test_audio = input("Enter path to test audio file: ").strip()

            try:
                result = client.identify_speaker(test_audio)
                print(f"✓ {result}")

                if result.matched:
                    print(f"  Matched: {result.speaker_name}")
                else:
                    print("  No match found (unknown speaker)")

                # Show top candidates
                print("\n  Top candidates:")
                for i, (sid, name, sim) in enumerate(result.get_top_candidates(5), 1):
                    print(f"    {i}. {name} ({sid}) - similarity: {sim:.4f}")

            except Exception as e:
                print(f"✗ Identification failed: {e}")

            # Example 3: List all speakers
            print("\n=== Example 3: List All Speakers ===")
            speakers = client.list_speakers()
            print(f"Total speakers: {len(speakers)}")
            for speaker in speakers:
                print(f"  - {speaker.speaker_name} ({speaker.speaker_id})")

            # Example 4: Verify a specific speaker
            if speakers:
                print("\n=== Example 4: Verify Speaker ===")
                speaker_id = speakers[0].speaker_id
                verify_audio = input(
                    f"Enter path to verification audio for {speakers[0].speaker_name}: "
                ).strip()

                try:
                    result = client.verify_speaker(verify_audio, speaker_id)
                    print(f"✓ {result}")

                except Exception as e:
                    print(f"✗ Verification failed: {e}")

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
