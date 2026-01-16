#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from pydantic import BaseModel, Field


class SileroVADConfig(BaseModel):
    """Configuration for Silero VAD extension."""

    # Model configuration
    use_onnx: bool = Field(
        default=True,
        description="Use ONNX model for faster inference (fallback to JIT if fails)"
    )
    sampling_rate: int = Field(
        default=16000,
        description="Audio sample rate (8000 or 16000)"
    )

    # VAD threshold parameters
    threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=0.9,
        description="Speech probability threshold (0.1-0.9, higher = less sensitive)"
    )
    min_speech_duration_ms: int = Field(
        default=250,
        ge=0,
        description="Minimum speech duration in milliseconds (filters short noise)"
    )
    min_silence_duration_ms: int = Field(
        default=100,
        ge=0,
        description="Minimum silence duration to end speech in milliseconds"
    )
    speech_pad_ms: int = Field(
        default=30,
        ge=0,
        description="Padding before/after speech in milliseconds"
    )

    # Processing configuration
    chunk_size: int = Field(
        default=512,
        gt=0,
        description="Audio chunk size in samples (512 = 32ms @ 16kHz)"
    )
    passthrough: bool = Field(
        default=True,
        description="Forward audio frames to output (set to False for VAD-only mode)"
    )

    # Debug configuration
    dump: bool = Field(
        default=False,
        description="Dump audio frames to file for debugging"
    )
    dump_path: str = Field(
        default="",
        description="Directory path for dumping audio files"
    )

    # ASR (Speech Recognition) configuration
    enable_asr: bool = Field(
        default=True,
        description="Enable ASR for speech interruption detection"
    )
    asr_model_dir: str = Field(
        default="speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx",
        description="FunASR model directory path"
    )
    asr_quantize: bool = Field(
        default=True,
        description="Use quantized ASR model for faster inference"
    )

    # Interruption detection configuration
    interruption_keywords_file: str = Field(
        default="interruption_keywords.json",
        description="Path to interruption keywords JSON file"
    )
    interruption_threshold: str = Field(
        default="medium",
        description="Minimum priority threshold for interruption (high/medium/low)"
    )
