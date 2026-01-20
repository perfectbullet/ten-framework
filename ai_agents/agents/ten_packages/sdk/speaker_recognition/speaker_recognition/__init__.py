#
# Speaker Recognition SDK
# A speaker recognition SDK using FunASR CampPlus model
#

from speaker_recognition.client import SpeakerRecognitionClient
from speaker_recognition.config import (
    SpeakerRecognitionConfig,
    ModelConfig,
    MongoDBConfig,
    MatcherConfig,
    AudioConfig,
)
from speaker_recognition.models import CampPlusModel
from speaker_recognition.storage import SpeakerStorage, SpeakerProfile
from speaker_recognition.matcher import SimilarityMatcher, MatchResult
from speaker_recognition.utils import SpeakerIdGenerator

__version__ = "0.1.0"

__all__ = [
    # Main client
    "SpeakerRecognitionClient",
    # Configuration
    "SpeakerRecognitionConfig",
    "ModelConfig",
    "MongoDBConfig",
    "MatcherConfig",
    "AudioConfig",
    # Core components
    "CampPlusModel",
    "SpeakerStorage",
    "SpeakerProfile",
    "SimilarityMatcher",
    "MatchResult",
    # Utilities
    "SpeakerIdGenerator",
]
