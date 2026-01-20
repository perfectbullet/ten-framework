#
# Tests for utility functions
#

import numpy as np
import pytest

from speaker_recognition.utils import (
    SpeakerIdGenerator,
    AudioUtils,
    format_similarity_score,
    get_confidence_level,
)


class TestSpeakerIdGenerator:
    """Tests for SpeakerIdGenerator."""

    def test_generate_format(self):
        """Test generated ID has correct format."""
        speaker_id = SpeakerIdGenerator.generate()

        # Should start with spkid_
        assert speaker_id.startswith("spkid_")

        # Should have 3 parts separated by underscore
        parts = speaker_id.split("_")
        assert len(parts) == 3

        # Timestamp part should be 12 digits
        assert len(parts[1]) == 12
        assert parts[1].isdigit()

        # Random suffix should be 4 characters
        assert len(parts[2]) == 4

    def test_generate_unique(self):
        """Test generated IDs are unique."""
        ids = [SpeakerIdGenerator.generate() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_is_valid_valid_id(self):
        """Test validation with valid IDs."""
        valid_ids = [
            "spkid_202501191430_a1b2",
            "spkid_202312312359_ffff",
            "spkid_202001010000_0000",
        ]
        for speaker_id in valid_ids:
            assert SpeakerIdGenerator.is_valid(speaker_id)

    def test_is_valid_invalid_id(self):
        """Test validation with invalid IDs."""
        invalid_ids = [
            None,
            "",
            "invalid",
            "spkid_",
            "spkid_20250119143_abc",  # Short timestamp
            "spkid_202501191430_abcde",  # Long suffix
            "spkid_202501191430_",  # Empty suffix
        ]
        for speaker_id in invalid_ids:
            assert not SpeakerIdGenerator.is_valid(speaker_id)


class TestAudioUtils:
    """Tests for AudioUtils."""

    def test_pcm_bytes_to_array(self):
        """Test converting PCM bytes to numpy array."""
        # Create sample int16 PCM data
        audio_data = np.array([1000, -1000, 500, -500], dtype=np.int16)
        pcm_bytes = audio_data.tobytes()

        result = AudioUtils.pcm_bytes_to_array(pcm_bytes)

        assert np.array_equal(result, audio_data)
        assert result.dtype == np.int16

    def test_int16_to_float32(self):
        """Test converting int16 to float32."""
        int16_audio = np.array([32767, 0, -32768], dtype=np.int16)
        result = AudioUtils.int16_to_float32(int16_audio)

        assert result.dtype == np.float32
        assert np.allclose(result, [1.0, 0.0, -1.0], atol=0.001)

    def test_float32_to_int16(self):
        """Test converting float32 to int16."""
        float_audio = np.array([1.0, 0.0, -1.0], dtype=np.float32)
        result = AudioUtils.float32_to_int16(float_audio)

        assert result.dtype == np.int16
        assert result[0] == 32767
        assert result[1] == 0
        assert result[2] == -32768

    def test_roundtrip_conversion(self):
        """Test roundtrip conversion preserves data."""
        original = np.random.randn(1000).astype(np.float32)
        original = np.clip(original, -1.0, 1.0)

        # Convert to int16 and back
        int16 = AudioUtils.float32_to_int16(original)
        back = AudioUtils.int16_to_float32(int16)

        # Should be close (allowing for quantization error)
        assert np.allclose(original, back, atol=1e-4)

    def test_validate_audio_valid(self):
        """Test audio validation with valid audio."""
        audio = np.random.randn(16000).astype(np.float32)  # 1 second at 16kHz
        assert AudioUtils.validate_audio(audio, 16000, min_duration=0.5)

    def test_validate_audio_too_short(self):
        """Test audio validation rejects short audio."""
        audio = np.random.randn(8000).astype(np.float32)  # 0.5 second at 16kHz
        assert not AudioUtils.validate_audio(audio, 16000, min_duration=1.0)

    def test_segment_audio(self):
        """Test audio segmentation."""
        # Create 6 seconds of audio at 16kHz
        audio = np.random.randn(96000).astype(np.float32)

        segments = AudioUtils.segment_audio(
            audio, 16000, segment_length=3.0, overlap=0.5
        )

        # Should get 3 segments with 50% overlap
        assert len(segments) == 3
        assert len(segments[0]) == 48000  # 3 seconds at 16kHz

    def test_aggregate_embeddings_mean(self):
        """Test embedding aggregation with mean."""
        embeddings = [
            np.array([1.0, 2.0, 3.0]),
            np.array([2.0, 3.0, 4.0]),
            np.array([3.0, 4.0, 5.0]),
        ]

        result = AudioUtils.aggregate_embeddings(embeddings, method="mean")
        expected = np.array([2.0, 3.0, 4.0])

        assert np.allclose(result, expected)

    def test_aggregate_embeddings_max(self):
        """Test embedding aggregation with max."""
        embeddings = [
            np.array([1.0, 2.0, 3.0]),
            np.array([2.0, 3.0, 4.0]),
            np.array([3.0, 4.0, 5.0]),
        ]

        result = AudioUtils.aggregate_embeddings(embeddings, method="max")
        expected = np.array([3.0, 4.0, 5.0])

        assert np.allclose(result, expected)

    def test_aggregate_embeddings_center(self):
        """Test embedding aggregation with center."""
        embeddings = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
            np.array([0.0, 0.0, 0.0]),
        ]

        result = AudioUtils.aggregate_embeddings(embeddings, method="center")
        # Should pick the center one (index 1 for 4 items)
        expected = np.array([0.0, 1.0, 0.0])

        assert np.allclose(result, expected)


class TestUtilityFunctions:
    """Tests for other utility functions."""

    def test_format_similarity_score(self):
        """Test similarity score formatting."""
        assert format_similarity_score(0.85) == "85.00%"
        assert format_similarity_score(1.0) == "100.00%"
        assert format_similarity_score(0.0) == "0.00%"
        assert format_similarity_score(0.7567) == "75.67%"

    def test_get_confidence_high(self):
        """Test high confidence level."""
        assert get_confidence_level(0.9) == "high"
        assert get_confidence_level(0.85) == "high"

    def test_get_confidence_medium(self):
        """Test medium confidence level."""
        assert get_confidence_level(0.8) == "medium"
        assert get_confidence_level(0.75) == "medium"

    def test_get_confidence_low(self):
        """Test low confidence level."""
        assert get_confidence_level(0.6) == "low"
        assert get_confidence_level(0.51) == "low"

    def test_get_confidence_none(self):
        """Test none confidence level."""
        assert get_confidence_level(0.3) == "none"
        assert get_confidence_level(0.0) == "none"

    def test_get_confidence_custom_thresholds(self):
        """Test confidence with custom thresholds."""
        result = get_confidence_level(
            0.8, high_threshold=0.9, medium_threshold=0.7
        )
        assert result == "medium"
