# Aliyun ASR BigModel Extension - AI Coding Agent Instructions

## Project Overview

This is a **TEN Framework extension** providing real-time ASR (Automatic Speech Recognition) with **dual backend support**:
- **Dashscope (Aliyun Cloud)** - Cloud-based ASR using Aliyun's BigModel service
- **FunASR (Local Server)** - Local ASR using self-hosted FunASR WebSocket server

Extensions communicate via async message passing within the larger multi-agent AI framework.

## Architecture & Key Patterns

### Dual Backend Architecture
- **Backend Selection**: Configured via `asr_backend` property ("dashscope" or "funasr")
- **Unified Interface**: Both backends implement compatible `Recognition`, `RecognitionCallback`, `RecognitionResult` interfaces
- **FunASR Adapter** (`funasr_adapter.py`): Wraps FunASR WebSocket client to match Dashscope's API surface
- **Conditional Instantiation**: `start_connection()` branches to `_start_dashscope_connection()` or `_start_funasr_connection()` based on config

### TEN Framework Extension Pattern
- Extensions inherit from `AsyncASRBaseExtension` (from `ten_ai_base.asr`)
- Lifecycle: `on_init` → `start_connection` → `send_audio` loop → `finalize` → `stop_connection` → `on_deinit`
- Must implement: `vendor()`, `buffer_strategy()`, `input_audio_sample_rate()`, `send_audio()`, `is_connected()`
- Use `AsyncTenEnv` for logging with categories: `LOG_CATEGORY_VENDOR`, `LOG_CATEGORY_KEY_POINT`

### Callback Threading Model (CRITICAL)
- **Dashscope**: SDK callbacks run on vendor threads, NOT the asyncio event loop
- **FunASR**: WebSocket receive thread calls callbacks directly
- Both use `asyncio.run_coroutine_threadsafe()` to bridge vendor/websocket threads to the extension's async loop
- `AliyunRecognitionCallback` (Dashscope) and `FunASRCallbackAdapter` (FunASR) both capture `asyncio.get_event_loop()` in `__init__`
- **Never** call extension methods directly from callbacks—always use `run_coroutine_threadsafe`

### FunASR Message Format Adaptation
- **Interim results**: `{'is_final': False, 'mode': '2pass-online', 'text': '...', 'wav_name': 'default'}`
- **Final results**: `{'is_final': True, 'mode': '2pass-offline', 'stamp_sents': [...], 'text': '...', 'timestamp': '...', 'wav_name': 'default'}`
- `FunASRRecognitionResult._build_output()` converts to Dashscope-compatible structure with `begin_time`, `end_time`, `words[]`
- Word-level timestamps extracted from `stamp_sents[0]['ts_list']` (solves the Dashscope limitation of empty `words[]`)

### Audio Timeline Management
- Tracks cumulative audio duration to map vendor-relative timestamps to absolute timeline
- `sent_user_audio_duration_ms_before_last_reset` accumulates duration across reconnections
- Audio duration calculated as: `len(bytes) / (sample_rate/1000 * 2)` (assumes 16-bit mono PCM)
- On reconnection (`on_asr_open`), previous timeline is preserved by adding to `sent_user_audio_duration_ms_before_last_reset`

### Finalization Modes
Two modes for ending recognition:
1. **`disconnect`**: Calls `recognition.stop()` immediately
2. **`mute_pkg`** (default): Sends silence PCM (`\x00` bytes) for `mute_pkg_duration_ms` to trigger final sentence from vendor

### Reconnection Strategy
- `ReconnectManager` handles exponential backoff: 300ms, 600ms, 1.2s, 2.4s, 4.8s (5 attempts max)
- Triggered on unexpected `on_asr_close` when `self.stopped == False`
- Connection marked successful in `on_asr_event` (first result received) to confirm full connection cycle

## Configuration

### Backend Selection
```python
asr_backend: str = "dashscope"  # "dashscope" (cloud) or "funasr" (local)
```

### Dashscope (Cloud) Configuration
```python
api_key: str  # Required, loaded from ${env:ALIYUN_ASR_BIGMODEL_API_KEY|}
model: str = "paraformer-realtime-v2"
language_hints: List[str] = ["en"]
finalize_mode: str = "mute_pkg"  # "disconnect" or "mute_pkg"
max_sentence_silence: int = 200  # ms (200-6000)
mute_pkg_duration_ms: int = 1000  # Must be > max_sentence_silence
vocabulary_list: List[Dict]  # Hot words for custom vocabulary
```

### FunASR (Local Server) Configuration
```python
funasr_host: str = "127.0.0.1"
funasr_port: str = "10095"
funasr_is_ssl: bool = False  # Use WSS (True) or WS (False)
funasr_chunk_size: str = "5,10,5"  # Chunk size parameters
funasr_chunk_interval: int = 10  # Chunk interval in milliseconds
funasr_mode: str = "2pass"  # "2pass", "offline", or "online"
funasr_hotwords: str = ""  # Format: "word1 weight\nword2 weight"
funasr_itn: bool = True  # Inverse text normalization
```

### Common Configuration
```python
sample_rate: int = 16000
dump: bool = False  # Save PCM to /tmp/aliyun_asr_bigmodel_in.pcm
```

## Development Workflows

### Running Tests
```bash
# From extension root directory
export PYTHONPATH=.ten/app:.ten/app/ten_packages/system/ten_runtime_python/lib:.ten/app/ten_packages/system/ten_runtime_python/interface:.ten/app/ten_packages/system/ten_ai_base/interface:$PYTHONPATH
pytest -s tests/
```

**Test Structure:**
- `conftest.py` - Session-scoped `FakeApp` provides TEN runtime context for tests
- `mock.py` - Patches `Recognition` class for unit tests without real vendor calls
- Test extension via `AsyncExtensionTester` and `AsyncTenEnvTester` from `ten_runtime`
- Tests send `AudioFrame` chunks and validate `ASRResult` data structure

### Adding New Features
1. **Audio processing changes**: Update `send_audio()` and timeline calculations
2. **New vendor parameters**: 
   - Dashscope: Add to `AliyunASRBigmodelConfig`, update `DashscopeRecognition()` in `_start_dashscope_connection()`
   - FunASR: Add to config, update `FunASRRecognition()` in `_start_funasr_connection()`
3. **Callback handling**: Add handler in callback adapter, forward to extension via `run_coroutine_threadsafe`
4. **Backend switching**: Test with both `asr_backend="dashscope"` and `asr_backend="funasr"` configurations

### Debugging Tips
- Use `dump: true` in config to save incoming PCM to `/tmp/aliyun_asr_bigmodel_in.pcm`
- Check `LOG_CATEGORY_VENDOR` logs for SDK-level events
- Monitor `sent_user_audio_duration_ms_before_last_reset` for timeline issues
- Verify `is_connected()` returns `True` before sending audio

## Common Patterns

### Error Handling
```python
# Non-fatal errors (vendor issues, retryable)
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.NON_FATAL_ERROR.value, message=msg),
    ModuleErrorVendorInfo(vendor=self.vendor(), code=vendor_code, message=vendor_msg)
)

# Fatal errors (API key missing, config invalid)
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.FATAL_ERROR.value, message=msg)
)
```

### Sensitive Data Logging
Always use `config.to_json(sensitive_handling=True)` to encrypt API keys in logs via `ten_ai_base.utils.encrypt()`

### AudioFrame Buffer Management
```python
buf = frame.lock_buf()
try:
    audio_data = bytes(buf)
    # ... process audio_data ...
finally:
    frame.unlock_buf(buf)  # ALWAYS unlock, even on exception
```

## Known Limitations & TODOs

From `代码解读.md`:
- **Word-level timestamps (Dashscope)**: `ASRResult.words` is always empty; FunASR provides populated `words[]` from `stamp_sents[0]['ts_list']`
- **Stereo audio**: Timeline calculation assumes mono (2 bytes/sample); stereo needs 4 bytes/sample
- **Reconnection success marking**: Currently marked on first `on_asr_event`; could be moved to `on_asr_open` for earlier feedback
- **FunASR vocabulary format**: Dashscope uses `List[Dict]` while FunASR uses string format `"word1 weight\nword2 weight"`—conversion needed if sharing configs

## Dependencies

- `dashscope==1.24.1` - Aliyun BigModel SDK
- `websocket-client` - WebSocket client for FunASR
- `pydantic` - Config validation
- TEN Framework packages: `ten_runtime_python`, `ten_ai_base` (defined in `manifest.json`)
