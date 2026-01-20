#
# Utility functions for Speaker Recognition SDK
#

import secrets
from datetime import datetime
from typing import Optional, Tuple, Union

import numpy as np
import torch


class SpeakerIdGenerator:
    """Generate speaker IDs in format: spkid_YYYYMMDDHHMM_RRRR."""

    @staticmethod
    def generate() -> str:
        """
        Generate a new speaker ID.

        Format: spkid_YYYYMMDDHHMM_RRRR
        - YYYYMMDDHHMM: Current timestamp
        - RRRR: 4 random hexadecimal characters

        Returns:
            Speaker ID string
        """
        now = datetime.now().strftime("%Y%m%d%H%M")
        random_suffix = secrets.token_hex(2).lower()  # 4 random characters
        return f"spkid_{now}_{random_suffix}"

    @staticmethod
    def is_valid(speaker_id: str) -> bool:
        """
        Validate speaker ID format.

        Args:
            speaker_id: Speaker ID to validate

        Returns:
            True if valid format
        """
        if not speaker_id or not isinstance(speaker_id, str):
            return False
        if not speaker_id.startswith("spkid_"):
            return False

        parts = speaker_id.split("_")
        if len(parts) != 3:
            return False

        # Check timestamp part (14 digits)
        timestamp = parts[1]
        if not timestamp.isdigit() or len(timestamp) != 12:
            return False

        # Check random suffix (4 hex characters)
        suffix = parts[2]
        if not suffix.isalnum() or len(suffix) != 4:
            return False

        return True


class AudioUtils:
    """Audio processing utilities."""

    @staticmethod
    def pcm_bytes_to_array(
        pcm_bytes: bytes, dtype: np.dtype = np.int16
    ) -> np.ndarray:
        """
        Convert PCM bytes to numpy array.

        Args:
            pcm_bytes: Raw PCM audio bytes
            dtype: Data type of PCM (default: int16)

        Returns:
            Audio array
        """
        return np.frombuffer(pcm_bytes, dtype=dtype)

    @staticmethod
    def int16_to_float32(audio: np.ndarray) -> np.ndarray:
        """
        Convert int16 audio to float32 normalized to [-1, 1].

        Args:
            audio: Input audio array (int16)

        Returns:
            Normalized float32 audio array
        """
        if audio.dtype == np.int16:
            return audio.astype(np.float32) / (1 << 15)
        elif audio.dtype == np.int32:
            return audio.astype(np.float32) / (1 << 31)
        elif audio.dtype == np.int8:
            return audio.astype(np.float32) / (1 << 7)
        else:
            return audio.astype(np.float32)

    @staticmethod
    def float32_to_int16(audio: np.ndarray) -> np.ndarray:
        """
        Convert float32 audio ([-1, 1]) to int16.

        Args:
            audio: Input float32 audio array

        Returns:
            int16 audio array
        """
        audio = np.clip(audio, -1.0, 1.0)
        return (audio * (1 << 15)).astype(np.int16)

    @staticmethod
    def load_audio_file(
        file_path: str, target_sr: int = 16000
    ) -> Tuple[np.ndarray, int]:
        """
        Load audio file and resample if needed.

        Args:
            file_path: Path to audio file
            target_sr: Target sample rate

        Returns:
            Tuple of (audio_array, sample_rate)
        """
        try:
            import librosa

            audio, sr = librosa.load(file_path, sr=target_sr, mono=True)
            return audio.astype(np.float32), sr
        except ImportError:
            # Fallback to soundfile
            import soundfile as sf

            audio, sr = sf.read(file_path)
            if len(audio.shape) == 2:
                audio = audio[:, 0]  # Convert to mono
            if sr != target_sr:
                from scipy.signal import resample

                audio = resample(audio, int(len(audio) * target_sr / sr))
            return audio.astype(np.float32), sr

    @staticmethod
    def validate_audio(
        audio: np.ndarray, sample_rate: int, min_duration: float = 1.0
    ) -> bool:
        """
        Validate audio has sufficient duration.

        Args:
            audio: Audio array
            sample_rate: Sample rate in Hz
            min_duration: Minimum duration in seconds

        Returns:
            True if valid
        """
        duration = len(audio) / sample_rate
        return duration >= min_duration

    @staticmethod
    def segment_audio(
        audio: np.ndarray,
        sample_rate: int,
        segment_length: float = 3.0,
        overlap: float = 0.5,
    ) -> list[np.ndarray]:
        """
        Segment audio into overlapping chunks.

        Args:
            audio: Audio array
            sample_rate: Sample rate in Hz
            segment_length: Length of each segment in seconds
            overlap: Overlap ratio (0-1)

        Returns:
            List of audio segments
        """
        segment_samples = int(segment_length * sample_rate)
        shift_samples = int(segment_samples * (1 - overlap))

        segments = []
        start = 0
        while start + segment_samples <= len(audio):
            end = start + segment_samples
            segments.append(audio[start:end])
            start += shift_samples

        # Handle remaining audio
        if start < len(audio) and len(segments) > 0:
            # Pad last segment if needed
            remaining = audio[start:]
            if len(remaining) > 0:
                padding = segment_samples - len(remaining)
                padded = np.pad(remaining, (0, padding), mode="constant")
                segments.append(padded)

        return segments

    @staticmethod
    def aggregate_embeddings(
        embeddings: list[np.ndarray], method: str = "mean"
    ) -> np.ndarray:
        """
        Aggregate multiple embeddings into one.

        Args:
            embeddings: List of embedding vectors
            method: Aggregation method ('mean', 'max', 'center')

        Returns:
            Aggregated embedding vector
        """
        if not embeddings:
            raise ValueError("No embeddings to aggregate")

        stacked = np.stack(embeddings)

        if method == "mean":
            return np.mean(stacked, axis=0)
        elif method == "max":
            return np.max(stacked, axis=0)
        elif method == "center":
            # Use center segment embedding
            center_idx = len(embeddings) // 2
            return embeddings[center_idx]
        else:
            raise ValueError(f"Unknown aggregation method: {method}")


class TensorUtils:
    """Tensor conversion utilities."""

    @staticmethod
    def numpy_to_tensor(audio: np.ndarray, device: str = "cpu") -> torch.Tensor:
        """Convert numpy array to tensor on specified device."""
        tensor = torch.from_numpy(audio).float()
        if device == "cuda" and torch.cuda.is_available():
            tensor = tensor.cuda()
        return tensor

    @staticmethod
    def tensor_to_numpy(tensor: torch.Tensor) -> np.ndarray:
        """Convert tensor to numpy array."""
        if tensor.is_cuda:
            tensor = tensor.cpu()
        return tensor.detach().numpy()


def format_similarity_score(score: float) -> str:
    """Format similarity score as percentage string."""
    return f"{score * 100:.2f}%"


def get_confidence_level(
    similarity: float, high_threshold: float = 0.85, medium_threshold: float = 0.75
) -> str:
    """
    Get confidence level based on similarity score.

    Args:
        similarity: Similarity score (0-1)
        high_threshold: Threshold for high confidence
        medium_threshold: Threshold for medium confidence

    Returns:
        Confidence level: 'high', 'medium', 'low', or 'none'
    """
    if similarity >= high_threshold:
        return "high"
    elif similarity >= medium_threshold:
        return "medium"
    elif similarity > 0.5:
        return "low"
    else:
        return "none"
