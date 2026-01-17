import copy
import os
from pydantic import BaseModel, Field
from typing import Any
from ten_ai_base import utils


class CosyTTSConfig(BaseModel):
    # Cosy TTS credentials
    api_key: str = ""  # Cosy TTS API Key

    # TTS specific configs
    model: str = ""  # Model name
    voice: str = ""  # Voice name
    sample_rate: int = 16000  # Audio sample rate

    # Local service settings
    use_local_service: bool = (
        False  # Use local CosyVoice service instead of online
    )
    local_service_url: str = (
        "ws://192.168.8.230:50002/streaming/ws"  # Local service WebSocket URL
    )
    local_spk_id: str = (
        ""  # Speaker ID for local service (will use 'voice' if not set)
    )

    # Debug and dump settings
    dump: bool = False
    dump_path: str = "/tmp"
    use_debug_audio: bool = False  # Use pre-recorded debug audio instead of TTS
    debug_audio_path: str = "/app/agents/examples/voice-assistant/zh-demo-emotion.wav"  # Path to debug audio file (WAV/PCM format, Docker path)

    # Parameters
    # Function reserved, currently empty, may need to add content later
    black_list_params: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)

    def is_black_list_params(self, key: str) -> bool:
        return key in self.black_list_params

    def to_str(self, sensitive_handling: bool = True) -> str:
        """Convert config to string with optional sensitive data handling."""
        if not sensitive_handling:
            return f"{self}"

        config = copy.deepcopy(self)

        # Encrypt sensitive fields
        if config.api_key:
            config.api_key = utils.encrypt(config.api_key)
        if config.params and "api_key" in config.params:
            config.params["api_key"] = utils.encrypt(config.params["api_key"])

        return f"{config}"

    def update_params(self) -> None:
        """Update config attributes from params dictionary."""
        param_names = [
            "api_key",
            "model",
            "sample_rate",
            "voice",
            "use_local_service",
            "local_service_url",
            "local_spk_id",
            "use_debug_audio",
            "debug_audio_path",
        ]

        for param_name in param_names:
            if param_name in self.params and not self.is_black_list_params(
                param_name
            ):
                setattr(self, param_name, self.params[param_name])

    def validate_params(self) -> None:
        """Validate required configuration parameters."""
        # If using debug audio, only validate debug audio path
        if self.use_debug_audio:
            if not self.debug_audio_path or self.debug_audio_path.strip() == "":
                raise ValueError(
                    "debug_audio_path is required when use_debug_audio is True"
                )
            # Skip file existence check - will be checked at runtime
            return

        if self.use_local_service:
            # For local service, only validate local-specific params
            required_fields = [
                "local_service_url",
                "voice",  # Will be used as spk_id if local_spk_id is not set
            ]
        else:
            # For online service, validate API key and model
            required_fields = [
                "api_key",
                "model",
                "voice",
            ]

        for field_name in required_fields:
            value = getattr(self, field_name)
            if not value or (isinstance(value, str) and value.strip() == ""):
                raise ValueError(
                    f"required fields are missing or empty: params.{field_name}"
                )
