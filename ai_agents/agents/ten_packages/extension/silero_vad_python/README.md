# Silero VAD Extension

Voice Activity Detection (VAD) extension for TEN Framework using [Silero VAD](https://github.com/snakers4/silero-vad).

## Features

- **Multi-language Support**: Supports 6000+ languages including Chinese
- **Low Latency**: Real-time processing with < 50ms delay
- **High Accuracy**: Excellent performance in various acoustic environments
- **Two Model Modes**: ONNX (faster, ~5MB) or JIT (fallback, ~2MB)
- **Audio Passthrough**: Forwards audio frames unchanged for downstream processing

## Installation

### Dependencies

```bash
# Core dependencies
pip install silero-vad>=5.1 torch>=1.12.0 torchaudio>=0.12.0

# Optional: ONNX runtime for faster inference
pip install onnxruntime>=1.16.1
```

### TEN Package Installation

```bash
cd /path/to/tenapp
tman install
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_onnx` | bool | `true` | Use ONNX model (faster) |
| `sampling_rate` | int | `16000` | Audio sample rate (8000 or 16000) |
| `threshold` | float | `0.5` | Speech probability threshold (0.1-0.9) |
| `min_speech_duration_ms` | int | `250` | Minimum speech length to trigger |
| `min_silence_duration_ms` | int | `100` | Silence duration to end speech |
| `speech_pad_ms` | int | `30` | Padding before/after speech |
| `chunk_size` | int | `512` | Audio chunk size in samples |
| `dump` | bool | `false` | Dump audio frames for debugging |
| `dump_path` | string | `""` | Directory for audio dumps |

### Parameter Tuning Guide

**Threshold (sensitivity):**
- **Quiet environments**: 0.3 - 0.4 (more sensitive)
- **Normal environments**: 0.5 (balanced)
- **Noisy environments**: 0.6 - 0.8 (less sensitive, fewer false triggers)

**Min Speech Duration (noise filtering):**
- Increase (e.g., 500ms) to filter out short sounds
- Default 250ms works well for most cases

**Min Silence Duration (speech end detection):**
- **Fast response**: 50-100ms (for conversational speech)
- **With pauses**: 200-500ms (for presentations/reading)
- **Long sentences**: 500-1000ms (only end on long pauses)

## Usage

### Graph Configuration

Add to your `property.json` predefined graph:

```json
{
  "ten": {
    "predefined_graphs": [{
      "name": "voice_assistant",
      "auto_start": true,
      "graph": {
        "nodes": [
          {
            "name": "vad",
            "addon": "silero_vad_python",
            "property": {
              "threshold": 0.5,
              "min_speech_duration_ms": 250,
              "min_silence_duration_ms": 100
            }
          },
          {
            "name": "stt",
            "addon": "deepgram_asr_python"
          }
        ],
        "connections": [
          {
            "extension": "vad",
            "audio_frame": [{
              "name": "pcm_frame",
              "dest": [{"extension": "stt"}]
            }]
          },
          {
            "extension": "main_control",
            "cmd": [{
              "names": ["start_of_sentence", "end_of_sentence"],
              "source": [{"extension": "vad"}]
            }]
          }
        ]
      }
    }]
  }
}
```

### API

**Audio Input:**
- Accepts `pcm_frame` audio frames
- Format: 16-bit PCM, mono, 8kHz or 16kHz

**Audio Output:**
- Forwards `pcm_frame` unchanged (passthrough)

**Commands Output:**
- `start_of_sentence` - Speech activity detected
- `end_of_sentence` - Speech ended (after silence period)

## Example: Handle VAD Events

```python
class MyExtension(AsyncExtension):
    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()

        if cmd_name == "start_of_sentence":
            ten_env.log_info("User started speaking")
            # Start recording, activate visual indicator, etc.

        elif cmd_name == "end_of_sentence":
            ten_env.log_info("User stopped speaking")
            # Process recorded audio, send to ASR, etc.
```

## Technical Details

### Audio Processing Pipeline

1. **Input**: 16-bit PCM audio frame (int16)
2. **Conversion**: int16 → float32 normalized to [-1, 1]
3. **VAD Detection**: Silero VAD model processes chunks (default 512 samples)
4. **Output**: Commands on speech state transitions

### Model Information

- **ONNX Mode**: ~5MB, faster inference (recommended)
- **JIT Mode**: ~2MB, PyTorch-based (fallback)
- Model is auto-downloaded on first use

## License

Apache License 2.0

## References

- [Silero VAD GitHub](https://github.com/snakers4/silero-vad)
- [TEN Framework Documentation](https://ten-framework.readthedocs.io/)
