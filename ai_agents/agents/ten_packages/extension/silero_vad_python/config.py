#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from pydantic import BaseModel, Field


class FSMNVADConfig(BaseModel):
    """Configuration for FSMN VAD extension."""

    # Model configuration
    model_dir: str = Field(
        default="speech_fsmn_vad_zh-cn-16k-common-pytorch",
        description="FunASR FSMN VAD model directory path (relative to extension dir)",
    )
    sampling_rate: int = Field(
        default=16000,
        description="Audio sample rate (must be 16000 for FSMN VAD)",
    )
    device: str = Field(
        default="cpu",
        description="Device for model inference (cpu or cuda)",
    )

    # Processing configuration
    chunk_size_ms: int = Field(
        default=200,
        gt=0,
        description="Audio chunk size in milliseconds (200ms = 3200 samples at 16kHz)",
    )
    passthrough: bool = Field(
        default=True,
        description="Forward audio frames to output (set to False for VAD-only mode)",
    )

    # Pre-buffer configuration
    pre_buffer_ms: int = Field(
        default=600,
        gt=0,
        description="Pre-buffer duration in ms. Audio before speech start is retained and sent to ASR.",
    )

    # Debug configuration
    dump: bool = Field(
        default=False,
        description="Dump audio frames to file for debugging",
    )
    dump_path: str = Field(
        default="",
        description="Directory path for dumping audio files",
    )

    # AGC/NS configuration (webrtc-audio-processing)
    enable_agc: bool = Field(
        default=True,
        description="Enable Automatic Gain Control",
    )
    enable_ns: bool = Field(
        default=True,
        description="Enable Noise Suppression",
    )
    agc_level: int = Field(
        default=1,
        description="AGC type (1=adaptive analog, 2/3 will kill low-volume signal)",
    )
    ns_level: int = Field(
        default=1,
        description="NS level 0-3 (1=low, 3 will kill low-volume speech)",
    )
