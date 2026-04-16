# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **FunASR ASR Extension** for the TEN Framework - a real-time Automatic Speech Recognition (ASR) extension that supports **FunASR local server** via WebSocket.

## Architecture

### Extension Structure

```
extension.py (AliyunASRBigmodelExtension)
    └── FunASR backend → funasr_adapter.py → FunASRRecognition
```

- `funasr_adapter.py` wraps FunASR WebSocket API to provide a clean interface
- `FunASRCallback` bridges WebSocket thread callbacks to the extension's asyncio event loop

### TEN Framework Extension Lifecycle

```
on_init → start_connection → send_audio loop → finalize → stop_connection → on_deinit
```

Required overrides from `AsyncASRBaseExtension`:
- `vendor()` - Returns "funasr_local"
- `buffer_strategy()` - Returns `ASRBufferConfigModeDiscard()`
- `input_audio_sample_rate()` - Returns configured sample rate
- `send_audio(frame, session_id)` - Sends PCM audio data
- `is_connected()` - Checks connection status

### Callback Threading Model (Critical)

FunASR WebSocket runs on a separate thread and calls callbacks from that thread, NOT the asyncio event loop.

All callbacks must bridge to the extension's asyncio loop using `asyncio.run_coroutine_threadsafe()`:
```python
# Callback stores event loop in __init__
self.loop = asyncio.get_event_loop()

# Callback uses thread-safe scheduling
asyncio.run_coroutine_threadsafe(
    self.extension.on_asr_event(), self.loop
)
```

Never call extension methods directly from callbacks without this bridge.

### Audio Timeline Management

- Tracks cumulative audio duration to map vendor-relative timestamps to absolute timeline
- `sent_user_audio_duration_ms_before_last_reset` accumulates duration across reconnections
- Audio duration formula: `bytes / (sample_rate/1000 * 2)` (assumes 16-bit mono PCM)
- Timeline resets on `on_asr_open` after preserving accumulated duration

## Configuration

### FunASR Configuration
```python
funasr_host: str = "127.0.0.1"
funasr_port: str = "10095"
funasr_is_ssl: bool = False
funasr_chunk_size: str = "5,10,5"
funasr_chunk_interval: int = 10
funasr_mode: str = "2pass"  # "2pass", "offline", "online"
funasr_hotwords: str = ""  # Format: "word1 weight\nword2 weight"
funasr_itn: bool = True
```

### Common Configuration
```python
language_hints: List[str] = ["zh"]
language: str = "zh-CN"
sample_rate: int = 16000
dump: bool = False  # Saves PCM to /tmp/aliyun_asr_bigmodel_in.pcm
```

## FunASR WebSocket Protocol

### Connection Init Message
```json
{
    "mode": "2pass",
    "chunk_size": [5, 10, 5],
    "encoder_chunk_look_back": 4,
    "decoder_chunk_look_back": 1,
    "chunk_interval": 10,
    "wav_name": "default",
    "is_speaking": true,
    "itn": true
}
```

### Intermediate Result (mode: 2pass-online)
```json
{
    "mode": "2pass-online",
    "text": "现在撤。",
    "wav_name": "default",
    "is_final": false
}
```

### Final Result (mode: 2pass-offline)
```json
{
    "mode": "2pass-offline",
    "text": "现在测试一下没有加入任何白噪声",
    "wav_name": "default",
    "is_final": true,
    "stamp_sents": [{
        "start": 880,
        "end": 5195,
        "text_seg": "现 在 测 试 ...",
        "ts_list": [[880, 1120], [1120, 1380], ...]
    }]
}
```

### Key Fields
- `mode`: "2pass-online" = intermediate result, "2pass-offline" = final result
- `is_final`: boolean, true indicates sentence end
- `stamp_sents`: contains word-level timestamps, only in final results
- `ts_list`: list of [start_time, end_time] for each word

## Development Commands

### Running Tests

```bash
# From extension root directory
export PYTHONPATH=.ten/app:.ten/app/ten_packages/system/ten_runtime_python/lib:.ten/app/ten_packages/system/ten_runtime_python/interface:.ten/app/ten_packages/system/ten_ai_base/interface:$PYTHONPATH

pytest -s tests/
```

### Protocol Verification

```bash
# Test FunASR connection directly
python funasr_client_api.py
```

### Adding New FunASR Parameters

Add to `AliyunASRBigmodelConfig`, then update `_start_funasr_connection()`:
```python
self.recognition = FunASRRecognition(
    new_param=self.config.new_param,  # Add here (via **kwargs)
    ...
)
```

## Key Patterns

### Error Handling

```python
# Non-fatal (vendor-side, retryable)
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.NON_FATAL_ERROR.value, message=msg),
    ModuleErrorVendorInfo(vendor=self.vendor(), code=vendor_code, message=vendor_msg)
)

# Fatal (configuration error, no retry)
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.FATAL_ERROR.value, message=msg)
)
```

### AudioFrame Buffer Management

```python
buf = frame.lock_buf()
try:
    audio_data = bytes(buf)
    # ... process audio_data ...
finally:
    frame.unlock_buf(buf)  # Always unlock, even on exception
```

## Reconnection Strategy

`ReconnectManager` implements exponential backoff:
- Delays: 300ms → 600ms → 1.2s → 2.4s → 4.8s
- Max 5 attempts
- Resets on successful connection (marked in `on_asr_event`)
- Triggered by unexpected `on_asr_close` when `self.stopped == False`

## Known Limitations

1. **Stereo audio**: Timeline calculation assumes mono (2 bytes/sample); stereo requires 4 bytes/sample
2. **Timestamp availability**: Word-level timestamps (`words[]`) only available in final results with `stamp_sents`

## Dependencies

```
websocket-client    # FunASR WebSocket client
websockets          # Alternative WebSocket client
pydantic            # Config validation
```

TEN Framework dependencies (in manifest.json):
- `ten_runtime_python` >= 0.11
- `ten_ai_base` >= 0.7
