# Speaker Recognition SDK

A Python SDK for speaker recognition using FunASR's CampPlus model. Supports speaker enrollment, identification, and verification with MongoDB storage.

## Features

- **Speaker Enrollment**: Register speakers with unique IDs
- **Speaker Identification**: Identify speakers from audio
- **Speaker Verification**: Verify if audio matches a specific speaker
- **MongoDB Storage**: Persistent speaker profile storage
- **Cosine Similarity Matching**: Fast and accurate similarity calculation
- **Batch Processing**: Support for multiple audio files

## Requirements

- Python 3.8+
- CUDA-capable GPU (optional, for faster inference)
- MongoDB database

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

## Quick Start

### Basic Usage

```python
from speaker_recognition import SpeakerRecognitionClient

# Create client
client = SpeakerRecognitionClient()

# Register a speaker
result = client.register_speaker(
    audio_path="/path/to/enrollment.wav",
    speaker_name="Alice"
)
print(f"Registered: {result.speaker_id}")

# Identify a speaker
result = client.identify_speaker("/path/to/test.wav")
if result.matched:
    print(f"Speaker: {result.speaker_name} (confidence: {result.confidence})")
else:
    print("Unknown speaker")

# Verify a specific speaker
result = client.verify_speaker("/path/to/test.wav", "spkid_202501191430_a1b2")
print(f"Verified: {result.is_valid} (similarity: {result.similarity:.3f})")
```

### Using Configuration File

```yaml
# config.yaml
model:
  device: "cuda"
  sample_rate: 16000

mongo:
  uri: "mongodb://speaker:speaker2026@192.168.8.233:27017/speaker?authSource=admin"
  database: "speaker"
  collection: "speakers"

matcher:
  similarity_threshold: 0.75
```

```python
from speaker_recognition import SpeakerRecognitionClient

client = SpeakerRecognitionClient(config_path="config.yaml")
```

### Registering from Audio Bytes

```python
# For raw PCM audio (int16 format)
with open("audio.pcm", "rb") as f:
    audio_bytes = f.read()

result = client.register_speaker_from_bytes(
    audio_bytes=audio_bytes,
    sample_rate=16000,
    speaker_name="Bob"
)
```

### Listing Speakers

```python
# List all speakers
speakers = client.list_speakers()
for speaker in speakers:
    print(f"{speaker.speaker_name} - {speaker.speaker_id}")

# Get count
count = client.count_speakers()
print(f"Total speakers: {count}")
```

## Speaker ID Format

Speaker IDs are generated in the format: `spkid_YYYYMMDDHHMM_RRRR`

- `YYYYMMDDHHMM`: Timestamp
- `RRRR`: 4 random hexadecimal characters

Example: `spkid_202501191430_a1b2`

## Configuration

### Model Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | str | FunASR path | Path to FunASR directory |
| `model_id` | str | iic/speech_campplus_sv_zh-cn_16k-common | Model ID |
| `device` | str | cuda | Device: cuda or cpu |
| `sample_rate` | int | 16000 | Audio sample rate (Hz) |
| `embedding_dim` | int | 192 | Embedding dimension |

### Matcher Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `similarity_threshold` | float | 0.75 | Threshold for positive match |
| `num_candidates` | int | 5 | Top-K candidates to return |
| `high_confidence` | float | 0.85 | High confidence threshold |
| `medium_confidence` | float | 0.75 | Medium confidence threshold |

### Audio Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_duration` | float | 1.0 | Minimum enrollment duration (seconds) |
| `segment_length` | float | 3.0 | Segment length for processing (seconds) |
| `segment_overlap` | float | 0.5 | Segment overlap ratio (0-1) |
| `aggregation` | str | mean | Embedding aggregation method |

## API Reference

### SpeakerRecognitionClient

#### Methods

- `register_speaker(audio_path, speaker_name, speaker_id=None, metadata=None)`
- `register_speaker_from_bytes(audio_bytes, sample_rate, speaker_name, speaker_id=None)`
- `identify_speaker(audio_path)`
- `identify_speaker_from_bytes(audio_bytes, sample_rate)`
- `verify_speaker(audio_path, speaker_id)`
- `verify_speaker_from_bytes(audio_bytes, sample_rate, speaker_id)`
- `delete_speaker(speaker_id)`
- `get_speaker(speaker_id)`
- `list_speakers(skip=0, limit=100)`
- `count_speakers()`

### Result Classes

- `RegistrationResult`: Result of speaker registration
- `IdentificationResult`: Result of speaker identification
- `VerificationResult`: Result of speaker verification

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_utils.py -v

# Run with coverage
pytest tests/ --cov=speaker_recognition

# Run performance benchmarks
pytest tests/test_performance.py -v -s -m benchmark
```

## Examples

See the `examples/` directory:

- `basic_usage.py`: Interactive example
- `register_and_identify.py`: Batch processing example

## Performance Targets

| Operation | Target |
|-----------|--------|
| Embedding extraction | < 100ms (3s audio) |
| Identification (100 speakers) | < 50ms |
| Similarity calculation | < 1ms |

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
