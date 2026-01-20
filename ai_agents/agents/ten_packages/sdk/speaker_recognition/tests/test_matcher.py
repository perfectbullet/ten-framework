#
# Tests for similarity matcher
#

import numpy as np
import pytest

from speaker_recognition.config import MatcherConfig
from speaker_recognition.matcher import (
    SimilarityMatcher,
    MatchResult,
    create_matcher,
    cosine_similarity,
)


class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        a = np.array([1.0, 2.0, 3.0])
        result = SimilarityMatcher.cosine_similarity(a, a)
        assert result == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        result = SimilarityMatcher.cosine_similarity(a, b)
        assert result == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Test cosine similarity of opposite vectors."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([-1.0, -2.0, -3.0])
        result = SimilarityMatcher.cosine_similarity(a, b)
        assert result == pytest.approx(-1.0)

    def test_similar_vectors(self):
        """Test cosine similarity of similar vectors."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.1, 2.1, 3.1])
        result = SimilarityMatcher.cosine_similarity(a, b)
        assert result > 0.95

    def test_192_dim_vectors(self):
        """Test cosine similarity with 192-dim vectors (embedding size)."""
        np.random.seed(42)
        a = np.random.randn(192)
        b = np.random.randn(192)
        result = SimilarityMatcher.cosine_similarity(a, b)
        assert -1 <= result <= 1


class TestSimilarityMatcher:
    """Tests for SimilarityMatcher."""

    def test_init_default(self):
        """Test initialization with default config."""
        matcher = SimilarityMatcher()
        assert matcher.threshold == 0.75
        assert matcher.high_threshold == 0.85
        assert matcher.medium_threshold == 0.75

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = MatcherConfig(
            similarity_threshold=0.8,
            high_confidence=0.9,
            medium_confidence=0.8,
        )
        matcher = SimilarityMatcher(config)
        assert matcher.threshold == 0.8
        assert matcher.high_threshold == 0.9
        assert matcher.medium_threshold == 0.8

    def test_find_best_match_above_threshold(self):
        """Test finding best match when similarity is above threshold."""
        matcher = SimilarityMatcher()

        # Create query and candidates
        query = np.array([1.0, 2.0, 3.0])
        candidates = {
            "spk_001": ("Alice", np.array([1.0, 2.0, 3.0])),  # Exact match
            "spk_002": ("Bob", np.array([-1.0, -2.0, -3.0])),  # Opposite
        }

        result = matcher.find_best_match(query, candidates)

        assert result.is_match()
        assert result.speaker_id == "spk_001"
        assert result.speaker_name == "Alice"
        assert result.similarity == pytest.approx(1.0)
        assert result.confidence == "high"

    def test_find_best_match_below_threshold(self):
        """Test finding best match when all similarities are below threshold."""
        matcher = SimilarityMatcher()

        # Create candidates all below threshold
        query = np.array([1.0, 2.0, 3.0])
        candidates = {
            "spk_001": ("Alice", np.array([-1.0, -2.0, -3.0])),  # Opposite
            "spk_002": ("Bob", np.array([0.0, 0.0, 0.0])),  # Zero
        }

        result = matcher.find_best_match(query, candidates)

        assert not result.is_match()
        assert result.speaker_id is None
        assert result.confidence == "none"

    def test_find_best_match_empty_candidates(self):
        """Test finding best match with no candidates."""
        matcher = SimilarityMatcher()
        query = np.array([1.0, 2.0, 3.0])

        result = matcher.find_best_match(query, {})

        assert not result.is_match()
        assert result.speaker_id is None
        assert result.top_k == []

    def test_find_best_match_top_k(self):
        """Test that top_k returns correct number of candidates."""
        matcher = SimilarityMatcher(MatcherConfig(num_candidates=3))

        query = np.array([1.0, 2.0, 3.0])
        candidates = {
            "spk_001": ("Alice", np.array([1.0, 2.0, 3.0])),
            "spk_002": ("Bob", np.array([1.1, 2.1, 3.1])),
            "spk_003": ("Charlie", np.array([-1.0, -2.0, -3.0])),
            "spk_004": ("David", np.array([0.0, 0.0, 0.0])),
        }

        result = matcher.find_best_match(query, candidates)

        # Should return top 3
        assert len(result.top_k) == 3
        # Top one should be Alice (exact match)
        assert result.top_k[0][0] == "spk_001"

    def test_verify_speaker_positive(self):
        """Test speaker verification with positive result."""
        matcher = SimilarityMatcher()

        query = np.array([1.0, 2.0, 3.0])
        speaker_emb = np.array([1.0, 2.0, 3.0])

        is_valid, similarity = matcher.verify_speaker(query, speaker_emb)

        assert is_valid
        assert similarity == pytest.approx(1.0)

    def test_verify_speaker_negative(self):
        """Test speaker verification with negative result."""
        matcher = SimilarityMatcher()

        query = np.array([1.0, 2.0, 3.0])
        speaker_emb = np.array([-1.0, -2.0, -3.0])

        is_valid, similarity = matcher.verify_speaker(query, speaker_emb)

        assert not is_valid
        assert similarity < 0

    def test_verify_speaker_custom_threshold(self):
        """Test speaker verification with custom threshold."""
        matcher = SimilarityMatcher()

        query = np.array([1.0, 2.0, 3.0])
        speaker_emb = np.array([0.9, 1.9, 2.9])

        # Should pass with default threshold
        is_valid, sim = matcher.verify_speaker(query, speaker_emb)
        assert is_valid

        # Should fail with higher threshold
        is_valid, sim = matcher.verify_speaker(query, speaker_emb, threshold=0.999)
        assert not is_valid

    def test_batch_match(self):
        """Test batch matching multiple queries."""
        matcher = SimilarityMatcher()

        candidates = {
            "spk_001": ("Alice", np.array([1.0, 2.0, 3.0])),
            "spk_002": ("Bob", np.array([-1.0, -2.0, -3.0])),
        }

        queries = [
            np.array([1.0, 2.0, 3.0]),
            np.array([-1.0, -2.0, -3.0]),
        ]

        results = matcher.batch_match(queries, candidates)

        assert len(results) == 2
        assert results[0].speaker_id == "spk_001"
        assert results[1].speaker_id == "spk_002"

    def test_set_threshold(self):
        """Test updating threshold."""
        matcher = SimilarityMatcher()

        assert matcher.threshold == 0.75

        matcher.set_threshold(0.8)
        assert matcher.threshold == 0.8
        assert matcher.config.similarity_threshold == 0.8

    def test_set_threshold_invalid(self):
        """Test setting invalid threshold raises error."""
        matcher = SimilarityMatcher()

        with pytest.raises(ValueError):
            matcher.set_threshold(1.5)

        with pytest.raises(ValueError):
            matcher.set_threshold(-1.5)


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_match_result_positive(self):
        """Test MatchResult for positive match."""
        result = MatchResult(
            speaker_id="spk_001",
            speaker_name="Alice",
            similarity=0.9,
            confidence="high",
            top_k=[("spk_001", "Alice", 0.9)],
        )

        assert result.is_match()
        assert str(result) == "Match: Alice (spk_001) - similarity: 0.9000, confidence: high"

    def test_match_result_negative(self):
        """Test MatchResult for no match."""
        result = MatchResult(
            speaker_id=None,
            speaker_name=None,
            similarity=0.5,
            confidence="none",
            top_k=[],
        )

        assert not result.is_match()
        assert "No match" in str(result)

    def test_get_top_speakers(self):
        """Test getting top speakers."""
        top_k = [
            ("spk_001", "Alice", 0.9),
            ("spk_002", "Bob", 0.8),
            ("spk_003", "Charlie", 0.7),
        ]
        result = MatchResult(
            speaker_id="spk_001",
            speaker_name="Alice",
            similarity=0.9,
            confidence="high",
            top_k=top_k,
        )

        top_2 = result.get_top_speakers(2)
        assert len(top_2) == 2
        assert top_2[0][0] == "spk_001"
        assert top_2[1][0] == "spk_002"


class TestCreateMatcher:
    """Tests for create_matcher convenience function."""

    def test_create_matcher_default(self):
        """Test creating matcher with default values."""
        matcher = create_matcher()
        assert isinstance(matcher, SimilarityMatcher)
        assert matcher.threshold == 0.75

    def test_create_matcher_custom(self):
        """Test creating matcher with custom values."""
        matcher = create_matcher(
            threshold=0.8,
            high_confidence=0.9,
            medium_confidence=0.8,
        )
        assert matcher.threshold == 0.8
        assert matcher.high_threshold == 0.9
        assert matcher.medium_threshold == 0.8
