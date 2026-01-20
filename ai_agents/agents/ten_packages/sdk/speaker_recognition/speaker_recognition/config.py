#
# Configuration classes for Speaker Recognition SDK
#

import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """CampPlus model configuration."""

    model_path: str = Field(
        default="/home/zj/zenking_work/FunASR",
        description="Path to FunASR directory or model identifier",
    )
    model_id: str = Field(
        default="iic/speech_campplus_sv_zh-cn_16k-common",
        description="Model ID for ModelScope/FunASR",
    )
    device: str = Field(default="cuda", description="Device to run model on: cuda or cpu")
    sample_rate: int = Field(default=16000, description="Audio sample rate in Hz")
    embedding_dim: int = Field(default=192, description="Embedding vector dimension")

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        if v not in ["cuda", "cpu"]:
            raise ValueError(f"device must be 'cuda' or 'cpu', got '{v}'")
        return v


class MongoDBConfig(BaseModel):
    """MongoDB connection configuration."""

    uri: str = Field(
        default="mongodb://speaker:speaker2026@192.168.8.233:27017/speaker?authSource=admin",
        description="MongoDB connection URI",
    )
    database: str = Field(default="speaker", description="Database name")
    collection: str = Field(default="speakers", description="Collection name")
    timeout_ms: int = Field(default=5000, description="Connection timeout in milliseconds")

    @classmethod
    def from_env(cls) -> "MongoDBConfig":
        """Create config from environment variables."""
        return cls(
            uri=os.getenv("SPEAKER_MONGO_URI", cls.__fields__["uri"].default),
            database=os.getenv("SPEAKER_MONGO_DATABASE", cls.__fields__["database"].default),
            collection=os.getenv("SPEAKER_MONGO_COLLECTION", cls.__fields__["collection"].default),
        )


class MatcherConfig(BaseModel):
    """Similarity matching configuration."""

    similarity_threshold: float = Field(
        default=0.75, ge=-1.0, le=1.0, description="Similarity threshold for positive match"
    )
    num_candidates: int = Field(
        default=5, ge=1, le=100, description="Number of top candidates to return"
    )

    # Confidence level thresholds
    high_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    medium_confidence: float = Field(default=0.75, ge=0.0, le=1.0)

    @field_validator("medium_confidence")
    @classmethod
    def validate_confidence_thresholds(cls, v: float, info) -> float:
        if "high_confidence" in info.data and v > info.data["high_confidence"]:
            raise ValueError("medium_confidence must be <= high_confidence")
        return v


class AudioConfig(BaseModel):
    """Audio processing configuration."""

    min_duration: float = Field(
        default=1.0, ge=0.1, description="Minimum audio duration in seconds for enrollment"
    )
    segment_length: float = Field(
        default=3.0, ge=0.5, description="Segment length in seconds for processing"
    )
    segment_overlap: float = Field(
        default=0.5, ge=0.0, lt=1.0, description="Segment overlap ratio (0-1)"
    )
    aggregation: str = Field(
        default="mean", description="Aggregation method for multiple embeddings: mean, max, center"
    )

    @field_validator("aggregation")
    @classmethod
    def validate_aggregation(cls, v: str) -> str:
        if v not in ["mean", "max", "center"]:
            raise ValueError(f"aggregation must be 'mean', 'max', or 'center', got '{v}'")
        return v


class SpeakerRecognitionConfig(BaseModel):
    """Main configuration for Speaker Recognition SDK."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    mongo: MongoDBConfig = Field(default_factory=MongoDBConfig)
    matcher: MatcherConfig = Field(default_factory=MatcherConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)

    @classmethod
    def from_yaml(cls, config_path: str) -> "SpeakerRecognitionConfig":
        """Load configuration from YAML file."""
        import yaml

        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls._parse_config(data)

    @classmethod
    def _parse_config(cls, data: Dict[str, Any]) -> "SpeakerRecognitionConfig":
        """Parse configuration dictionary."""
        return cls(
            model=ModelConfig(**data.get("model", {})),
            mongo=MongoDBConfig(**data.get("mongo", {})),
            matcher=MatcherConfig(**data.get("matcher", {})),
            audio=AudioConfig(**data.get("audio", {})),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpeakerRecognitionConfig":
        """Create configuration from dictionary."""
        return cls._parse_config(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "model": self.model.model_dump(),
            "mongo": self.mongo.model_dump(),
            "matcher": self.matcher.model_dump(),
            "audio": self.audio.model_dump(),
        }
