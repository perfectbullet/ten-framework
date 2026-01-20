#
# Pytest configuration and fixtures for Speaker Recognition SDK tests
#

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

# Add SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def sample_embedding():
    """Generate a sample 192-dim embedding vector."""
    np.random.seed(42)
    return np.random.randn(192).astype(np.float32)


@pytest.fixture(scope="session")
def sample_embeddings():
    """Generate multiple sample embedding vectors."""
    np.random.seed(42)
    return {
        "speaker_001": ("Alice", np.random.randn(192).astype(np.float32)),
        "speaker_002": ("Bob", np.random.randn(192).astype(np.float32)),
        "speaker_003": ("Charlie", np.random.randn(192).astype(np.float32)),
    }


@pytest.fixture(scope="session")
def sample_audio_16k():
    """Generate a 16kHz sample audio array (3 seconds)."""
    sample_rate = 16000
    duration = 3.0
    np.random.seed(42)
    # Generate random noise as "audio"
    audio = np.random.randn(int(sample_rate * duration)).astype(np.float32) * 0.1
    return audio, sample_rate


@pytest.fixture
def mock_model():
    """Create a mock CampPlus model."""
    model = MagicMock()
    model.config = MagicMock()
    model.config.device = "cpu"
    model.config.embedding_dim = 192
    model.get_device.return_value = "cpu"

    # Mock extract_embedding to return sample data
    def mock_extract(audio, sr=16000):
        np.random.seed(42)
        return np.random.randn(192).astype(np.float32)

    model.extract_embedding.side_effect = mock_extract
    return model


@pytest.fixture
def mock_storage():
    """Create a mock MongoDB storage."""
    storage = MagicMock()
    storage.config = MagicMock()

    # Mock speaker database
    storage._speakers = {}

    def mock_register(speaker_id, speaker_name, embedding, metadata=None):
        from datetime import datetime

        if speaker_id in storage._speakers:
            raise ValueError(f"Speaker {speaker_id} already exists")
        storage._speakers[speaker_id] = {
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "embedding": embedding,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": metadata or {},
        }
        return storage._speakers[speaker_id]

    def mock_get_speaker(speaker_id):
        return storage._speakers.get(speaker_id)

    def mock_get_all_embeddings():
        return {
            k: (v["speaker_name"], np.array(v["embedding"]))
            for k, v in storage._speakers.items()
        }

    def mock_delete_speaker(speaker_id):
        return storage._speakers.pop(speaker_id, None) is not None

    def mock_count():
        return len(storage._speakers)

    def mock_exists(speaker_id):
        return speaker_id in storage._speakers

    storage.register_speaker.side_effect = mock_register
    storage.get_speaker.side_effect = mock_get_speaker
    storage.get_all_embeddings.side_effect = mock_get_all_embeddings
    storage.delete_speaker.side_effect = mock_delete_speaker
    storage.count_speakers.side_effect = mock_count
    storage.speaker_exists.side_effect = mock_exists
    storage.list_speakers.return_value = list(storage._speakers.values())

    return storage


@pytest.fixture
def model_config():
    """Create model configuration for testing."""
    from speaker_recognition.config import ModelConfig

    return ModelConfig(device="cpu")


@pytest.fixture
def matcher_config():
    """Create matcher configuration for testing."""
    from speaker_recognition.config import MatcherConfig

    return MatcherConfig(similarity_threshold=0.75)


@pytest.fixture
def mongo_config():
    """Create MongoDB configuration for testing."""
    from speaker_recognition.config import MongoDBConfig

    return MongoDBConfig(
        database="speaker_test",
        collection="speakers_test",
    )


@pytest.fixture
def skip_if_no_mongo():
    """Skip test if MongoDB is not available."""
    try:
        from pymongo import MongoClient

        client = MongoClient(
            "mongodb://speaker:speaker2026@192.168.8.233:27017/?authSource=admin",
            serverSelectionTimeoutMS=2000,
        )
        client.admin.command("ping")
        return True
    except Exception:
        pytest.skip("MongoDB not available")


@pytest.fixture
def skip_if_no_model():
    """Skip test if FunASR model is not available."""
    try:
        from funasr import AutoModel

        # Try to load model
        model = AutoModel(
            model="iic/speech_campplus_sv_zh-cn_16k-common",
            device="cpu",
        )
        return True
    except Exception:
        pytest.skip("FunASR model not available")


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "mongo: Tests requiring MongoDB")
    config.addinivalue_line("markers", "model: Tests requiring FunASR model")
