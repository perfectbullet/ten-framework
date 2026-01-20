#
# Audio preprocessing and embedding extraction utilities
#

import logging
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np

from speaker_recognition.audio import AudioConfig, AudioUtils
from speaker_recognition.models import CampPlusModel

logger = logging.getLogger(__name__)


class AudioPreprocessor:
    """Audio preprocessing for speaker recognition."""

    def __init__(self, config: Optional[AudioConfig] = None):
        """
        Initialize audio preprocessor.

        Args:
            config: Audio processing configuration
        """
        self.config = config or AudioConfig()

    def load_audio(
        self, audio_input: Union[str, np.ndarray, bytes], sample_rate: int = 16000
    ) -> Tuple[np.ndarray, int]:
        """
        Load audio from various input types.

        Args:
            audio_input: Audio input - can be:
                - File path (str)
                - numpy array
                - PCM bytes (bytes)
            sample_rate: Target sample rate

        Returns:
            Tuple of (audio_array, actual_sample_rate)
        """
        if isinstance(audio_input, str):
            # Load from file path
            audio, sr = AudioUtils.load_audio_file(audio_input, sample_rate)
            return audio, sr

        elif isinstance(audio_input, bytes):
            # Convert PCM bytes to array
            audio = AudioUtils.pcm_bytes_to_array(audio_input)
            audio = AudioUtils.int16_to_float32(audio)
            return audio, sample_rate

        elif isinstance(audio_input, np.ndarray):
            # Already a numpy array
            audio = audio_input.astype(np.float32)
            if audio.dtype != np.float32:
                audio = AudioUtils.int16_to_float32(audio)
            return audio, sample_rate

        else:
            raise ValueError(
                f"Unsupported audio input type: {type(audio_input)}. "
                "Expected str (file path), numpy array, or bytes."
            )

    def validate_audio(
        self, audio: np.ndarray, sample_rate: int, is_enrollment: bool = True
    ) -> bool:
        """
        Validate audio meets requirements.

        Args:
            audio: Audio array
            sample_rate: Sample rate in Hz
            is_enrollment: True if this is for enrollment (stricter validation)

        Returns:
            True if audio is valid
        """
        min_duration = self.config.min_duration if is_enrollment else 0.5
        if not AudioUtils.validate_audio(audio, sample_rate, min_duration):
            logger.warning(
                f"Audio too short: {len(audio) / sample_rate:.2f}s "
                f"(minimum: {min_duration}s)"
            )
            return False
        return True

    def preprocess_audio(
        self, audio: np.ndarray, sample_rate: int
    ) -> Tuple[np.ndarray, int]:
        """
        Preprocess audio for embedding extraction.

        Args:
            audio: Input audio array
            sample_rate: Sample rate in Hz

        Returns:
            Tuple of (processed_audio, sample_rate)
        """
        # Ensure float32 and normalized
        if audio.dtype != np.float32:
            audio = AudioUtils.int16_to_float32(audio)

        # Check sample rate
        if sample_rate != self.config.model_sample_rate:
            logger.warning(
                f"Audio sample rate {sample_rate} differs from "
                f"model rate {self.config.model_sample_rate}. "
                "Resampling may be needed."
            )

        return audio, sample_rate


class EmbeddingExtractor:
    """High-level embedding extraction interface."""

    def __init__(
        self,
        model: CampPlusModel,
        preprocessor: Optional[AudioPreprocessor] = None,
        config: Optional[AudioConfig] = None,
    ):
        """
        Initialize embedding extractor.

        Args:
            model: CampPlus model instance
            preprocessor: Audio preprocessor (created if None)
            config: Audio processing configuration
        """
        self.model = model
        self.preprocessor = preprocessor or AudioPreprocessor(config)
        self.config = config or AudioConfig()

    def extract_from_file(
        self, file_path: str, validate: bool = True
    ) -> Optional[np.ndarray]:
        """
        Extract embedding from audio file.

        Args:
            file_path: Path to audio file
            validate: Whether to validate audio before extraction

        Returns:
            192-dim embedding vector or None if validation fails
        """
        audio, sr = self.preprocessor.load_audio(file_path)

        if validate and not self.preprocessor.validate_audio(audio, sr):
            return None

        return self.model.extract_embedding(audio, sr)

    def extract_from_bytes(
        self, audio_bytes: bytes, sample_rate: int = 16000, validate: bool = True
    ) -> Optional[np.ndarray]:
        """
        Extract embedding from raw audio bytes.

        Args:
            audio_bytes: Raw PCM audio bytes
            sample_rate: Sample rate in Hz
            validate: Whether to validate audio before extraction

        Returns:
            192-dim embedding vector or None if validation fails
        """
        audio, sr = self.preprocessor.load_audio(audio_bytes, sample_rate)

        if validate and not self.preprocessor.validate_audio(audio, sr):
            return None

        return self.model.extract_embedding(audio, sr)

    def extract_from_array(
        self, audio: np.ndarray, sample_rate: int = 16000, validate: bool = True
    ) -> Optional[np.ndarray]:
        """
        Extract embedding from numpy array.

        Args:
            audio: Audio array
            sample_rate: Sample rate in Hz
            validate: Whether to validate audio before extraction

        Returns:
            192-dim embedding vector or None if validation fails
        """
        audio, sr = self.preprocessor.load_audio(audio, sample_rate)

        if validate and not self.preprocessor.validate_audio(audio, sr, is_enrollment=False):
            return None

        return self.model.extract_embedding(audio, sr)

    def extract_with_aggregation(
        self,
        audio_input: Union[str, np.ndarray, bytes],
        sample_rate: int = 16000,
        aggregation: Optional[str] = None,
    ) -> Optional[np.ndarray]:
        """
        Extract embedding with segment aggregation.

        Audio is segmented into overlapping chunks, embeddings are extracted
        from each segment, then aggregated using the specified method.

        Args:
            audio_input: Audio input (file path, array, or bytes)
            sample_rate: Sample rate in Hz
            aggregation: Aggregation method (mean, max, center).
                        Uses config default if None.

        Returns:
            Aggregated 192-dim embedding vector
        """
        audio, sr = self.preprocessor.load_audio(audio_input, sample_rate)

        if not self.preprocessor.validate_audio(audio, sr):
            return None

        # Segment audio
        segments = AudioUtils.segment_audio(
            audio,
            sr,
            segment_length=self.config.segment_length,
            overlap=self.config.segment_overlap,
        )

        if not segments:
            logger.warning("No segments generated from audio")
            return None

        # Extract embeddings from each segment
        embeddings = []
        for i, segment in enumerate(segments):
            try:
                emb = self.model.extract_embedding(segment, sr)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(f"Failed to extract embedding from segment {i}: {e}")

        if not embeddings:
            logger.error("Failed to extract any embeddings")
            return None

        # Aggregate embeddings
        agg_method = aggregation or self.config.aggregation
        return AudioUtils.aggregate_embeddings(embeddings, method=agg_method)

    def extract_for_enrollment(
        self,
        audio_input: Union[str, np.ndarray, bytes],
        sample_rate: int = 16000,
        num_segments: Optional[int] = None,
    ) -> Optional[np.ndarray]:
        """
        Extract embedding optimized for enrollment.

        Uses segmentation and aggregation for more robust enrollment.

        Args:
            audio_input: Audio input (file path, array, or bytes)
            sample_rate: Sample rate in Hz
            num_segments: Number of segments to extract (auto if None)

        Returns:
            192-dim embedding vector suitable for enrollment
        """
        return self.extract_with_aggregation(audio_input, sample_rate)


def create_extractor(
    model: Optional[CampPlusModel] = None,
    config: Optional[AudioConfig] = None,
) -> EmbeddingExtractor:
    """
    Convenience function to create embedding extractor.

    Args:
        model: CampPlus model (created if None)
        config: Audio configuration

    Returns:
        EmbeddingExtractor instance
    """
    if model is None:
        from speaker_recognition.models import create_model

        model = create_model()

    return EmbeddingExtractor(model, config=config)
