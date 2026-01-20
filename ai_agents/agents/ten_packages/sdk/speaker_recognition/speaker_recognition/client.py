#
# Main client API for Speaker Recognition SDK
#

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from speaker_recognition.utils import AudioUtils, SpeakerIdGenerator
from speaker_recognition.config import (
    AudioConfig,
    MatcherConfig,
    ModelConfig,
    MongoDBConfig,
    SpeakerRecognitionConfig,
)
from speaker_recognition.extractor import EmbeddingExtractor
from speaker_recognition.matcher import MatchResult, SimilarityMatcher
from speaker_recognition.models import CampPlusModel
from speaker_recognition.storage import SpeakerProfile, SpeakerStorage

logger = logging.getLogger(__name__)


@dataclass
class RegistrationResult:
    """Result of speaker registration."""

    speaker_id: str
    speaker_name: str
    embedding: np.ndarray
    created_at: datetime
    audio_duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"Registered: {self.speaker_name} ({self.speaker_id}) "
            f"at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )


@dataclass
class IdentificationResult:
    """Result of speaker identification."""

    matched: bool
    speaker_id: Optional[str]
    speaker_name: Optional[str]
    similarity: float
    confidence: str  # "high", "medium", "low", "none"
    top_k: List[Tuple[str, str, float]] = field(default_factory=list)
    # Format: [(speaker_id, speaker_name, similarity), ...]

    def __str__(self) -> str:
        if self.matched:
            return (
                f"Identified: {self.speaker_name} ({self.speaker_id}) "
                f"- similarity: {self.similarity:.4f}, confidence: {self.confidence}"
            )
        return f"Unknown speaker - closest similarity: {self.similarity:.4f}"

    def get_top_candidates(self, n: int = 5) -> List[Tuple[str, str, float]]:
        """Get top N candidate speakers."""
        return self.top_k[:n]


@dataclass
class VerificationResult:
    """Result of speaker verification."""

    is_valid: bool
    similarity: float
    threshold: float
    speaker_id: str

    def __str__(self) -> str:
        status = "Valid" if self.is_valid else "Invalid"
        return (
            f"{status}: similarity={self.similarity:.4f}, "
            f"threshold={self.threshold:.4f}, speaker={self.speaker_id}"
        )


class SpeakerRecognitionClient:
    """
    High-level API for speaker recognition.

    Supports:
    - Speaker enrollment (registration)
    - Speaker identification
    - Speaker verification
    """

    def __init__(
        self,
        config: Optional[SpeakerRecognitionConfig] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize speaker recognition client.

        Args:
            config: Configuration object
            config_path: Path to YAML configuration file
        """
        # Load configuration
        if config_path:
            self.config = SpeakerRecognitionConfig.from_yaml(config_path)
        else:
            self.config = config or SpeakerRecognitionConfig()

        # Initialize components
        self.model: Optional[CampPlusModel] = None
        self.extractor: Optional[EmbeddingExtractor] = None
        self.storage: Optional[SpeakerStorage] = None
        self.matcher: Optional[SimilarityMatcher] = None

        self._initialized = False

    def initialize(self):
        """Initialize all components (lazy initialization)."""
        if self._initialized:
            return

        logger.info("Initializing Speaker Recognition Client...")

        # Initialize model
        self.model = CampPlusModel(self.config.model)
        logger.info(f"Model loaded on device: {self.model.get_device()}")

        # Initialize extractor
        from speaker_recognition.extractor import AudioPreprocessor

        preprocessor = AudioPreprocessor(self.config.audio)
        self.extractor = EmbeddingExtractor(self.model, preprocessor, self.config.audio)

        # Initialize storage
        self.storage = SpeakerStorage(self.config.mongo)
        logger.info(f"Connected to MongoDB: {self.config.mongo.database}")

        # Initialize matcher
        self.matcher = SimilarityMatcher(self.config.matcher)
        logger.info(f"Matcher initialized with threshold: {self.config.matcher.similarity_threshold}")

        self._initialized = True
        logger.info("Speaker Recognition Client initialized successfully")

    def _ensure_initialized(self):
        """Ensure client is initialized."""
        if not self._initialized:
            self.initialize()

    # ==================== Registration ====================

    def register_speaker(
        self,
        audio_path: str,
        speaker_name: str,
        speaker_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegistrationResult:
        """
        Register a new speaker.

        Args:
            audio_path: Path to enrollment audio file
            speaker_name: Speaker display name
            speaker_id: Optional custom ID (auto-generated if None)
            metadata: Optional metadata dictionary

        Returns:
            RegistrationResult with speaker_id and embedding info

        Raises:
            ValueError: If audio validation fails or speaker_id already exists
        """
        self._ensure_initialized()

        # Generate speaker ID if not provided
        if speaker_id is None:
            speaker_id = SpeakerIdGenerator.generate()

        # Validate speaker ID
        if not SpeakerIdGenerator.is_valid(speaker_id):
            raise ValueError(f"Invalid speaker_id format: {speaker_id}")

        # Check if speaker already exists
        if self.storage.speaker_exists(speaker_id):
            raise ValueError(f"Speaker with ID '{speaker_id}' already exists")

        # Extract embedding (with aggregation for robustness)
        embedding = self.extractor.extract_for_enrollment(audio_path)

        if embedding is None:
            raise ValueError(
                "Failed to extract embedding. "
                "Check audio file format and duration."
            )

        # Calculate audio duration
        audio, sr = AudioUtils.load_audio_file(audio_path)
        duration = len(audio) / sr

        # Prepare metadata
        final_metadata = metadata or {}
        final_metadata["enrollment_duration"] = duration
        final_metadata["enrollment_sample_rate"] = sr

        # Register in database
        profile = self.storage.register_speaker(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            embedding=embedding,
            metadata=final_metadata,
        )

        logger.info(f"Successfully registered speaker: {speaker_id} ({speaker_name})")

        return RegistrationResult(
            speaker_id=profile.speaker_id,
            speaker_name=profile.speaker_name,
            embedding=np.array(profile.embedding),
            created_at=profile.created_at,
            audio_duration=duration,
            metadata=final_metadata,
        )

    def register_speaker_from_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        speaker_name: str,
        speaker_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegistrationResult:
        """
        Register a speaker from raw audio bytes.

        Args:
            audio_bytes: Raw PCM audio bytes (int16 format)
            sample_rate: Sample rate in Hz
            speaker_name: Speaker display name
            speaker_id: Optional custom ID (auto-generated if None)
            metadata: Optional metadata dictionary

        Returns:
            RegistrationResult
        """
        self._ensure_initialized()

        # Generate speaker ID if not provided
        if speaker_id is None:
            speaker_id = SpeakerIdGenerator.generate()

        # Validate speaker ID
        if not SpeakerIdGenerator.is_valid(speaker_id):
            raise ValueError(f"Invalid speaker_id format: {speaker_id}")

        # Check if speaker already exists
        if self.storage.speaker_exists(speaker_id):
            raise ValueError(f"Speaker with ID '{speaker_id}' already exists")

        # Convert bytes to array
        audio = AudioUtils.pcm_bytes_to_array(audio_bytes)
        audio = AudioUtils.int16_to_float32(audio)

        # Validate audio duration
        duration = len(audio) / sample_rate
        if duration < self.config.audio.min_duration:
            raise ValueError(
                f"Audio too short: {duration:.2f}s "
                f"(minimum: {self.config.audio.min_duration}s)"
            )

        # Extract embedding with aggregation
        embedding = self.extractor.extract_from_array(audio, sample_rate)

        if embedding is None:
            raise ValueError("Failed to extract embedding from audio bytes")

        # Prepare metadata
        final_metadata = metadata or {}
        final_metadata["enrollment_duration"] = duration
        final_metadata["enrollment_sample_rate"] = sample_rate
        final_metadata["enrollment_source"] = "bytes"

        # Register in database
        profile = self.storage.register_speaker(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            embedding=embedding,
            metadata=final_metadata,
        )

        logger.info(f"Successfully registered speaker from bytes: {speaker_id}")

        return RegistrationResult(
            speaker_id=profile.speaker_id,
            speaker_name=profile.speaker_name,
            embedding=np.array(profile.embedding),
            created_at=profile.created_at,
            audio_duration=duration,
            metadata=final_metadata,
        )

    # ==================== Identification ====================

    def identify_speaker(self, audio_path: str) -> IdentificationResult:
        """
        Identify speaker from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            IdentificationResult with matched speaker or None
        """
        self._ensure_initialized()

        # Get all registered speakers
        candidates = self.storage.get_all_embeddings()

        if not candidates:
            logger.warning("No registered speakers in database")
            return IdentificationResult(
                matched=False,
                speaker_id=None,
                speaker_name=None,
                similarity=0.0,
                confidence="none",
            )

        # Extract embedding from query audio
        embedding = self.extractor.extract_from_file(audio_path)

        if embedding is None:
            logger.error("Failed to extract embedding from audio")
            return IdentificationResult(
                matched=False,
                speaker_id=None,
                speaker_name=None,
                similarity=0.0,
                confidence="none",
            )

        # Find best match
        match_result = self.matcher.find_best_match(embedding, candidates)

        logger.info(f"Identification result: {match_result}")

        return IdentificationResult(
            matched=match_result.is_match(),
            speaker_id=match_result.speaker_id,
            speaker_name=match_result.speaker_name,
            similarity=match_result.similarity,
            confidence=match_result.confidence,
            top_k=match_result.top_k,
        )

    def identify_speaker_from_bytes(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> IdentificationResult:
        """
        Identify speaker from raw audio bytes.

        Args:
            audio_bytes: Raw PCM audio bytes (int16 format)
            sample_rate: Sample rate in Hz

        Returns:
            IdentificationResult
        """
        self._ensure_initialized()

        # Get all registered speakers
        candidates = self.storage.get_all_embeddings()

        if not candidates:
            logger.warning("No registered speakers in database")
            return IdentificationResult(
                matched=False,
                speaker_id=None,
                speaker_name=None,
                similarity=0.0,
                confidence="none",
            )

        # Convert bytes to array
        audio = AudioUtils.pcm_bytes_to_array(audio_bytes)
        audio = AudioUtils.int16_to_float32(audio)

        # Extract embedding
        embedding = self.extractor.extract_from_array(audio, sample_rate)

        if embedding is None:
            logger.error("Failed to extract embedding from audio bytes")
            return IdentificationResult(
                matched=False,
                speaker_id=None,
                speaker_name=None,
                similarity=0.0,
                confidence="none",
            )

        # Find best match
        match_result = self.matcher.find_best_match(embedding, candidates)

        return IdentificationResult(
            matched=match_result.is_match(),
            speaker_id=match_result.speaker_id,
            speaker_name=match_result.speaker_name,
            similarity=match_result.similarity,
            confidence=match_result.confidence,
            top_k=match_result.top_k,
        )

    # ==================== Verification ====================

    def verify_speaker(
        self, audio_path: str, speaker_id: str
    ) -> VerificationResult:
        """
        Verify if audio matches specific speaker.

        Args:
            audio_path: Path to audio file
            speaker_id: Speaker ID to verify against

        Returns:
            VerificationResult with is_valid and similarity score
        """
        self._ensure_initialized()

        # Get speaker profile
        profile = self.storage.get_speaker(speaker_id)

        if profile is None:
            raise ValueError(f"Speaker not found: {speaker_id}")

        # Extract embedding from query audio
        embedding = self.extractor.extract_from_file(audio_path)

        if embedding is None:
            logger.error("Failed to extract embedding from audio")
            return VerificationResult(
                is_valid=False,
                similarity=0.0,
                threshold=self.matcher.threshold,
                speaker_id=speaker_id,
            )

        # Verify against stored embedding
        speaker_embedding = np.array(profile.embedding)
        is_valid, similarity = self.matcher.verify_speaker(embedding, speaker_embedding)

        logger.info(
            f"Verification for {speaker_id}: valid={is_valid}, "
            f"similarity={similarity:.4f}"
        )

        return VerificationResult(
            is_valid=is_valid,
            similarity=similarity,
            threshold=self.matcher.threshold,
            speaker_id=speaker_id,
        )

    def verify_speaker_from_bytes(
        self, audio_bytes: bytes, sample_rate: int, speaker_id: str
    ) -> VerificationResult:
        """
        Verify if audio bytes match specific speaker.

        Args:
            audio_bytes: Raw PCM audio bytes
            sample_rate: Sample rate in Hz
            speaker_id: Speaker ID to verify against

        Returns:
            VerificationResult
        """
        self._ensure_initialized()

        # Get speaker profile
        profile = self.storage.get_speaker(speaker_id)

        if profile is None:
            raise ValueError(f"Speaker not found: {speaker_id}")

        # Convert bytes and extract embedding
        audio = AudioUtils.pcm_bytes_to_array(audio_bytes)
        audio = AudioUtils.int16_to_float32(audio)
        embedding = self.extractor.extract_from_array(audio, sample_rate)

        if embedding is None:
            return VerificationResult(
                is_valid=False,
                similarity=0.0,
                threshold=self.matcher.threshold,
                speaker_id=speaker_id,
            )

        # Verify
        speaker_embedding = np.array(profile.embedding)
        is_valid, similarity = self.matcher.verify_speaker(embedding, speaker_embedding)

        return VerificationResult(
            is_valid=is_valid,
            similarity=similarity,
            threshold=self.matcher.threshold,
            speaker_id=speaker_id,
        )

    # ==================== Management ====================

    def delete_speaker(self, speaker_id: str) -> bool:
        """
        Delete speaker from database.

        Args:
            speaker_id: Speaker ID to delete

        Returns:
            True if deleted, False if not found
        """
        self._ensure_initialized()
        return self.storage.delete_speaker(speaker_id)

    def get_speaker(self, speaker_id: str) -> Optional[SpeakerProfile]:
        """
        Get speaker profile by ID.

        Args:
            speaker_id: Speaker ID

        Returns:
            SpeakerProfile or None if not found
        """
        self._ensure_initialized()
        return self.storage.get_speaker(speaker_id)

    def list_speakers(
        self, skip: int = 0, limit: int = 100
    ) -> List[SpeakerProfile]:
        """
        List all registered speakers.

        Args:
            skip: Number of speakers to skip
            limit: Maximum number of speakers to return

        Returns:
            List of SpeakerProfile objects
        """
        self._ensure_initialized()
        return self.storage.list_speakers(skip=skip, limit=limit)

    def count_speakers(self) -> int:
        """
        Get total count of registered speakers.

        Returns:
            Number of speakers
        """
        self._ensure_initialized()
        return self.storage.count_speakers()

    def update_threshold(self, threshold: float):
        """
        Update similarity threshold.

        Args:
            threshold: New threshold value (0-1)
        """
        self._ensure_initialized()
        self.matcher.set_threshold(threshold)

    def close(self):
        """Close resources (database connection, etc.)."""
        if self.storage:
            self.storage.close()
        self._initialized = False

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def create_client(
    config_path: Optional[str] = None,
    model_device: str = "cuda",
    similarity_threshold: float = 0.75,
    mongo_uri: Optional[str] = None,
) -> SpeakerRecognitionClient:
    """
    Convenience function to create speaker recognition client.

    Args:
        config_path: Path to YAML configuration file
        model_device: Device for model (cuda or cpu)
        similarity_threshold: Similarity threshold for matching
        mongo_uri: MongoDB connection URI (overrides config)

    Returns:
        SpeakerRecognitionClient instance
    """
    if config_path:
        return SpeakerRecognitionClient(config_path=config_path)

    # Create custom config
    config = SpeakerRecognitionConfig(
        model=ModelConfig(device=model_device),
        matcher=MatcherConfig(similarity_threshold=similarity_threshold),
    )

    if mongo_uri:
        config.mongo.uri = mongo_uri

    return SpeakerRecognitionClient(config=config)
