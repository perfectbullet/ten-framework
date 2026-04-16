from typing import Any, Dict, List
from pydantic import BaseModel, Field
from dataclasses import dataclass


@dataclass
class AliyunASRBigmodelConfig(BaseModel):
    # Backend selection - fixed to funasr
    asr_backend: str = "funasr"

    # FunASR (Local Server) configuration
    funasr_host: str = "127.0.0.1"
    funasr_port: str = "10095"
    funasr_is_ssl: bool = False
    funasr_chunk_size: str = "5,10,5"  # Chunk size parameters for FunASR
    funasr_chunk_interval: int = 10  # Chunk interval in milliseconds
    funasr_mode: str = "2pass"  # Recognition mode: "2pass", "offline", "online"
    funasr_hotwords: str = ""  # Hot words in format "word1 weight\nword2 weight"
    funasr_itn: bool = True  # Inverse text normalization

    # Common configuration
    language_hints: List[str] = Field(default_factory=lambda: ["zh"])
    language: str = "zh-CN"
    sample_rate: int = 16000
    dump: bool = False
    dump_path: str = "/tmp"
    params: Dict[str, Any] = Field(default_factory=dict)

    def update(self, params: Dict[str, Any]) -> None:
        """Update configuration with additional parameters."""
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_json(self, sensitive_handling: bool = False) -> str:
        """Convert config to JSON string."""
        config_dict = self.model_dump()
        return str(config_dict)

    @property
    def normalized_language(self):
        if self.language_hints and len(self.language_hints) > 0:
            lang = self.language_hints[0]
            if lang == "zh":
                return "zh-CN"
            elif lang == "en":
                return "en-US"
            elif lang == "ja":
                return "ja-JP"
            elif lang == "ko":
                return "ko-KR"
            elif lang == "de":
                return "de-DE"
            elif lang == "fr":
                return "fr-FR"
            elif lang == "ru":
                return "ru-RU"
            else:
                return lang
        return self.language
