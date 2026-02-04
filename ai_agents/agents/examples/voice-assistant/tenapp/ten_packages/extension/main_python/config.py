import os
from pydantic import BaseModel


class OllamaConfig(BaseModel):
    """Ollama client configuration for semantic validation (from environment variables)."""

    enabled: bool = True
    base_url: str = "http://192.168.8.233:11434"
    model: str = "qwen2.5:7b"
    timeout: float = 5.0

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("OLLAMA_ENABLED", "true").lower() in ("true", "1", "yes"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://192.168.8.233:11434"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "5.0")),
        )


class MainControlConfig(BaseModel):
    greeting: str = "Hello, I am your AI assistant."
