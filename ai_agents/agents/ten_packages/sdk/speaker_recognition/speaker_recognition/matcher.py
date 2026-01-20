#
# Speaker similarity matching module
#

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from speaker_recognition.config import MatcherConfig

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Speaker recognition match result."""

    speaker_id: Optional[str]
    speaker_name: Optional[str]
    similarity: float
    confidence: str  # "high", "medium", "low", "none"
    top_k: List[Tuple[str, str, float]] = field(default_factory=list)
    # Format: [(speaker_id, speaker_name, similarity), ...]

    def is_match(self) -> bool:
        """Check if this result represents a positive match."""
        return self.speaker_id is not None and self.confidence != "none"

    def get_top_speakers(self, n: int = 5) -> List[Tuple[str, str, float]]:
        """Get top N candidates."""
        return self.top_k[:n]

    def __str__(self) -> str:
        if self.is_match():
            return (
                f"Match: {self.speaker_name} ({self.speaker_id}) "
                f"- similarity: {self.similarity:.4f}, confidence: {self.confidence}"
            )
        return f"No match - closest similarity: {self.similarity:.4f}"


class SimilarityMatcher:
    """Speaker similarity matching using cosine similarity."""

    def __init__(self, config: Optional[MatcherConfig] = None):
        """
        Initialize similarity matcher.

        Args:
            config: Matcher configuration
        """
        self.config = config or MatcherConfig()
        self.threshold = self.config.similarity_threshold
        self.high_threshold = self.config.high_confidence
        self.medium_threshold = self.config.medium_confidence

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Similarity score in range [-1, 1]
        """
        # Ensure numpy arrays
        if not isinstance(a, np.ndarray):
            a = np.array(a)
        if not isinstance(b, np.ndarray):
            b = np.array(b)

        # Handle different shapes
        if a.ndim == 2:
            a = a.squeeze()
        if b.ndim == 2:
            b = b.squeeze()

        # Compute cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def compute_similarity_matrix(
        self, query_embedding: np.ndarray, embedding_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Compute similarities between query and multiple embeddings.

        Args:
            query_embedding: Query embedding vector (D,)
            embedding_matrix: Matrix of embeddings (N, D)

        Returns:
            Array of similarity scores (N,)
        """
        # Normalize embeddings
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        matrix_norm = embedding_matrix / (
            np.linalg.norm(embedding_matrix, axis=1, keepdims=True) + 1e-8
        )

        # Compute dot products
        similarities = np.dot(matrix_norm, query_norm)
        return similarities

    def find_best_match(
        self, query_embedding: np.ndarray, candidates: Dict[str, Tuple[str, np.ndarray]]
    ) -> MatchResult:
        """
        Find best matching speaker from candidates.

        Args:
            query_embedding: Query embedding vector (192-dim)
            candidates: Dictionary mapping speaker_id to (speaker_name, embedding)

        Returns:
            MatchResult with best match or None if below threshold
        """
        if not candidates:
            return MatchResult(None, None, 0.0, "none", [])

        # Compute similarities for all candidates
        scores = []
        for speaker_id, (speaker_name, embedding) in candidates.items():
            sim = self.cosine_similarity(query_embedding, embedding)
            scores.append((speaker_id, speaker_name, sim))

        # Sort by similarity (descending)
        scores.sort(key=lambda x: x[2], reverse=True)

        # Get top K
        top_k = scores[: self.config.num_candidates]

        # Check if best match meets threshold
        if scores[0][2] >= self.threshold:
            best = scores[0]
            confidence = self._get_confidence_level(best[2])
            return MatchResult(
                speaker_id=best[0],
                speaker_name=best[1],
                similarity=best[2],
                confidence=confidence,
                top_k=top_k,
            )

        # No match above threshold
        return MatchResult(
            speaker_id=None,
            speaker_name=None,
            similarity=scores[0][2],
            confidence="none",
            top_k=top_k,
        )

    def find_all_matches(
        self, query_embedding: np.ndarray, candidates: Dict[str, Tuple[str, np.ndarray]]
    ) -> List[Tuple[str, str, float, bool]]:
        """
        Find all matches (both above and below threshold).

        Args:
            query_embedding: Query embedding vector
            candidates: Dictionary mapping speaker_id to (speaker_name, embedding)

        Returns:
            List of tuples (speaker_id, speaker_name, similarity, is_match)
        """
        results = []
        for speaker_id, (speaker_name, embedding) in candidates.items():
            sim = self.cosine_similarity(query_embedding, embedding)
            is_match = sim >= self.threshold
            results.append((speaker_id, speaker_name, sim, is_match))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def batch_match(
        self,
        query_embeddings: List[np.ndarray],
        candidates: Dict[str, Tuple[str, np.ndarray]],
    ) -> List[MatchResult]:
        """
        Match multiple query embeddings against candidates.

        Args:
            query_embeddings: List of query embedding vectors
            candidates: Dictionary mapping speaker_id to (speaker_name, embedding)

        Returns:
            List of MatchResult objects
        """
        results = []
        for query_emb in query_embeddings:
            result = self.find_best_match(query_emb, candidates)
            results.append(result)
        return results

    def verify_speaker(
        self,
        query_embedding: np.ndarray,
        speaker_embedding: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Tuple[bool, float]:
        """
        Verify if query embedding matches specific speaker embedding.

        Args:
            query_embedding: Query embedding to verify
            speaker_embedding: Reference speaker embedding
            threshold: Optional custom threshold (uses default if None)

        Returns:
            Tuple of (is_verified, similarity_score)
        """
        thr = threshold if threshold is not None else self.threshold
        similarity = self.cosine_similarity(query_embedding, speaker_embedding)
        is_verified = similarity >= thr
        return is_verified, similarity

    def _get_confidence_level(self, similarity: float) -> str:
        """
        Get confidence level based on similarity score.

        Args:
            similarity: Similarity score (0-1)

        Returns:
            Confidence level: 'high', 'medium', 'low', or 'none'
        """
        if similarity >= self.high_threshold:
            return "high"
        elif similarity >= self.medium_threshold:
            return "medium"
        elif similarity > 0.5:
            return "low"
        else:
            return "none"

    def set_threshold(self, threshold: float):
        """
        Update similarity threshold.

        Args:
            threshold: New threshold value (0-1)
        """
        if not -1 <= threshold <= 1:
            raise ValueError(f"Threshold must be in [-1, 1], got {threshold}")
        self.threshold = threshold
        self.config.similarity_threshold = threshold


def create_matcher(
    threshold: float = 0.75,
    high_confidence: float = 0.85,
    medium_confidence: float = 0.75,
) -> SimilarityMatcher:
    """
    Convenience function to create similarity matcher.

    Args:
        threshold: Similarity threshold for positive match
        high_confidence: Threshold for high confidence level
        medium_confidence: Threshold for medium confidence level

    Returns:
        SimilarityMatcher instance
    """
    config = MatcherConfig(
        similarity_threshold=threshold,
        high_confidence=high_confidence,
        medium_confidence=medium_confidence,
    )
    return SimilarityMatcher(config)
