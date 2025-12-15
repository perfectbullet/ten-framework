# TEN Framework - Aliyun ASR Extension

## Architecture Overview

This is a **TEN Framework extension** that integrates Aliyun's Dashscope ASR (Automatic Speech Recognition) service. TEN Framework uses an addon-based architecture where:

- **Extensions** are runtime components that process data streams (audio, video, text)
- **Addons** are factories that create extension instances
- **AsyncASRBaseExtension** is the base class providing the ASR interface contract

### Key Components

1. **addon.py** - Entry point using `@register_addon_as_extension` decorator
2. **extension.py** - Core `AliyunASRBigmodelExtension` class with async lifecycle
3. **config.py** - Pydantic-based configuration with env variable support
4. **reconnect_manager.py** - Exponential backoff retry logic (5 attempts: 300ms, 600ms, 1.2s, 2.4s, 4.8s)
5. **AliyunRecognitionCallback** - Bridges vendor callbacks to asyncio event loop

## Critical Patterns

### Thread-Safe Callback Bridge
The vendor SDK (Dashscope) runs callbacks in separate threads. Bridge them to the extension's asyncio loop:

```python
class AliyunRecognitionCallback(RecognitionCallback):
    def __init__(self, extension_instance):
        self.loop = asyncio.get_event_loop()  # Capture main loop
    
    def on_event(self, result):
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_event(result), self.loop
        )
```

### Audio Timeline Management
Vendor timestamps are **relative to last connection**. Map to absolute timeline:

```python
# On reconnect, preserve history
self.sent_user_audio_duration_ms_before_last_reset += self.audio_timeline.get_total_user_audio_duration()
self.audio_timeline.reset()

# When processing results
absolute_time = audio_timeline.get_audio_duration_before_time(vendor_begin_time) + sent_user_audio_duration_ms_before_last_reset
```

### Finalize Modes
Two strategies for session end:
- **disconnect**: Immediately call `recognition.stop()`
- **mute_pkg**: Send silent PCM (`b"\x00" * samples`) to trigger natural sentence end

The `mute_pkg_duration_ms` must exceed `max_sentence_silence` to reliably trigger finalization.

### Frame Buffer Lifecycle
Always use lock/unlock pattern with proper error handling:

```python
buf = frame.lock_buf()
try:
    audio_data = bytes(buf)
    # Process audio_data
finally:
    frame.unlock_buf(buf)  # MUST unlock even on error
```

## Configuration

- Load from environment: `api_key: "${env:ALIYUN_ASR_BIGMODEL_API_KEY|}"`
- Merge patterns: Default config → property.json → runtime params
- Use `config.to_json(sensitive_handling=True)` for logging (encrypts secrets)

### Key Settings
- `model`: Default `"paraformer-realtime-v2"`
- `sample_rate`: 16000 (16-bit PCM mono assumed)
- `max_sentence_silence`: 200-6000ms, controls sentence segmentation
- `vocabulary_list`: Custom hotwords via `VocabularyService.create_vocabulary`

## Testing

Tests use `AsyncExtensionTester` with a fake TEN app runtime:

```python
tester = AliyunASRBigmodelExtensionTester()
tester.set_test_mode_single("aliyun_asr_bigmodel_python", json.dumps(property_json))
err = tester.run()
```

- **conftest.py**: Runs fake app in background thread, blocks test start until `on_init`
- Audio simulation: Read PCM file in chunks (320 bytes), send via `send_audio_frame`
- Validation: Check `asr_result` data structure (id, text, is_final, stream_id, etc.)

## Common Workflows

### Run Tests
```bash
pytest tests/test_asr_result.py -v
pytest tests/test_invalid_params.py -v
```

### Debug Connection Issues
1. Check `vendor_status_changed: on_open/on_close` logs (category: `vendor`)
2. Verify `reconnect_manager.get_attempts_info()` shows remaining retries
3. Look for `vendor_error` logs with status codes from Dashscope

### Add New Configuration Parameter
1. Add field to `AliyunASRBigmodelConfig` in `config.py`
2. Update `manifest.json` → `api.property.properties.params.properties`
3. Pass to `Recognition()` constructor in `start_connection()`

## Dependencies

- `ten_runtime_python`: TEN Framework core (v0.11+)
- `ten_ai_base`: ASR interface contracts and utilities (v0.7+)
- `dashscope`: Aliyun SDK (v1.24.1)

Import paths like `../../system/ten_ai_base/api/asr-interface.json` reference shared contract definitions in the larger TEN Framework monorepo structure.

## Anti-Patterns

❌ **Don't** call vendor SDK methods directly in lifecycle hooks - wrap in connection management
❌ **Don't** assume single-threaded execution - use `asyncio.run_coroutine_threadsafe`
❌ **Don't** send audio after `finalize()` in disconnect mode - connection is closed
❌ **Don't** forget to reset timeline counters on reconnect - causes timestamp drift

## Error Handling

- **Fatal errors**: Connection exhausted, invalid API key → Send `ModuleErrorCode.FATAL_ERROR`
- **Non-fatal errors**: Transient network issues → Send `ModuleErrorCode.NON_FATAL_ERROR` with vendor info
- Always include `ModuleErrorVendorInfo` with vendor-specific codes for debugging
