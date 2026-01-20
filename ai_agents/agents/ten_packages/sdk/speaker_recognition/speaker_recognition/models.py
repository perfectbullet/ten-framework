#
# CampPlus model wrapper for Speaker Recognition SDK
#

import logging
from typing import Optional, Union

import numpy as np
import torch

from speaker_recognition.config import ModelConfig

logger = logging.getLogger(__name__)


class CampPlusModel:
    """
    CampPlus model wrapper for speaker embedding extraction.

    Uses FunASR's AutoModel to load the CampPlus model.
    """

    def __init__(self, config: ModelConfig):
        """
        Initialize CampPlus model.

        Args:
            config: Model configuration
        """
        self.config = config
        self.model = None
        self.device = self._get_device()
        self._load_model()

    def _get_device(self) -> str:
        """Get actual device to use."""
        if self.config.device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, using CPU")
            return "cpu"
        return self.config.device

    def _load_model(self):
        """Load CampPlus model from FunASR."""
        try:
            from funasr import AutoModel

            logger.info(
                f"Loading CampPlus model: {self.config.model_id} on {self.device}"
            )

            # Load model using FunASR AutoModel
            self.model = AutoModel(
                model=self.config.model_id,
                device=self.device,
            )

            logger.info("CampPlus model loaded successfully")
        except ImportError as e:
            raise ImportError(
                "FunASR is not installed. Please install it with: pip install funasr"
            ) from e
        except Exception as e:
            logger.error(f"Failed to load CampPlus model: {e}")
            raise

    def extract_embedding(
        self,
        audio: Union[np.ndarray, str, list],
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """
        Extract speaker embedding from audio.

        Args:
            audio: Input audio - can be:
                - numpy array (float32, normalized to [-1, 1])
                - file path (str)
                - list of audio arrays
            sample_rate: Sample rate in Hz (used if audio is array)

        Returns:
            192-dim embedding vector
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Prepare input for FunASR
        if isinstance(audio, str):
            # File path - pass directly to FunASR
            input_data = audio
        elif isinstance(audio, np.ndarray):
            # Convert numpy array to the format expected by FunASR
            # FunASR expects raw audio data or file path
            input_data = {"speech": audio, "fs": sample_rate}
        elif isinstance(audio, list):
            # List of audio arrays
            input_data = [{"speech": a, "fs": sample_rate} for a in audio]
        else:
            raise ValueError(
                f"Unsupported audio type: {type(audio)}. "
                "Expected numpy array, file path string, or list."
            )

        # Generate embedding using FunASR
        try:
            result = self.model.generate(
                input=input_data,
                batch_size_s=300,
                key1="speech",
                fs=sample_rate,
            )

            # Extract embedding from result
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0].get("spk_embedding")
                if embedding is not None:
                    if isinstance(embedding, torch.Tensor):
                        embedding = embedding.cpu().numpy()
                    if embedding.ndim == 2:
                        embedding = embedding.squeeze(0)
                    return embedding.astype(np.float32)

            raise ValueError("Failed to extract embedding from model output")

        except Exception as e:
            logger.error(f"Error extracting embedding: {e}")
            raise

    def extract_embedding_batch(
        self, audio_list: list[np.ndarray], sample_rate: int = 16000
    ) -> np.ndarray:
        """
        Extract embeddings from multiple audio files.

        Args:
            audio_list: List of audio arrays
            sample_rate: Sample rate in Hz

        Returns:
            Array of shape (N, 192) where N is number of audio files
        """
        embeddings = []
        for audio in audio_list:
            emb = self.extract_embedding(audio, sample_rate)
            embeddings.append(emb)
        return np.stack(embeddings)

    def get_embedding_dim(self) -> int:
        """Get embedding dimension."""
        return self.config.embedding_dim

    def get_device(self) -> str:
        """Get device being used."""
        return self.device

    def to(self, device: str):
        """Move model to device (if applicable)."""
        logger.warning(
            f"Device change requested: {self.device} -> {device}. "
            "Note: FunASR AutoModel manages device internally."
        )
        self.config.device = device
        self.device = self._get_device()
        return self


def create_model(
    model_id: Optional[str] = None,
    device: str = "cuda",
    model_path: Optional[str] = None,
) -> CampPlusModel:
    """
    Convenience function to create CampPlus model.

    Args:
        model_id: Model ID (default: iic/speech_campplus_sv_zh-cn_16k-common)
        device: Device to use (cuda or cpu)
        model_path: Path to FunASR directory

    Returns:
        CampPlusModel instance
    """
    config = ModelConfig(
        model_path=model_path or "/home/zj/zenking_work/FunASR",
        model_id=model_id or "iic/speech_campplus_sv_zh-cn_16k-common",
        device=device,
    )
    return CampPlusModel(config)
