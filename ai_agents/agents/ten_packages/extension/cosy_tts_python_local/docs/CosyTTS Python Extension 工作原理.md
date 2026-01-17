# CosyTTS Python Extension 工作原理

`cosy_tts_python_local` 是 TEN Framework 中的一个 TTS 扩展，用于集成 Cosy TTS 服务。它基于异步架构，支持流式音频合成。

## 核心架构

### 1. 扩展结构
扩展继承自 `AsyncTTS2BaseExtension`，实现标准的 TTS 接口 [1](#0-0) ：

```python
class CosyTTSExtension(AsyncTTS2BaseExtension):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.client: CosyTTSClient | None = None
        self.config: CosyTTSConfig | None = None
        # ... 其他状态变量
```

### 2. 生命周期管理
扩展遵循标准的 TEN 生命周期 [2](#0-1) ：
- `on_init()`: 加载配置，初始化 TTS 客户端
- `on_start()`: 启动扩展
- `on_stop()`: 停止音频处理任务，清理资源
- `on_deinit()`: 最终清理

## TTS 请求处理流程

### 1. 请求接收
通过 `request_tts()` 方法处理 TTS 文本输入 [3](#0-2) ：

```python
async def request_tts(self, t: TTSTextInput) -> None:
    # 检查请求 ID 变化，管理状态
    if t.request_id != self.current_request_id:
        # 重置状态，管理 PCM writer
        self.current_request_id = t.request_id
        self.current_request_finished = False
        # ...

    # 发送文本到 TTS 服务
    self.client.synthesize_audio(t.text, t.text_input_end)
```

### 2. 音频处理
独立的音频处理循环 `_process_audio_data()` 在后台运行 [4](#0-3) ：

```python
async def _process_audio_data(self) -> None:
    while True:
        done, message_type, data = await self.client.get_audio_data()

        if message_type == MESSAGE_TYPE_PCM:
            # 处理音频数据，发送到图
            await self.send_tts_audio_data(audio_chunk)

        if done:
            # 处理请求结束
            await self._handle_tts_audio_end()
```

## Cosy TTS 客户端实现

### 1. 客户端架构
`CosyTTSClient` 使用 dashscope SDK 与 Cosy TTS 服务通信 [5](#0-4) ：

```python
class CosyTTSClient:
    def __init__(self, config: CosyTTSConfig, ten_env: AsyncTenEnv, vendor: str):
        self.config = config
        self.ten_env = ten_env
        dashscope.api_key = config.api_key

    def start(self) -> None:
        self._callback = AsyncIteratorCallback(self.ten_env, self._receive_queue)
        self.synthesizer = SpeechSynthesizer(
            callback=self._callback,
            format=self._get_audio_format(),
            model=self.config.model,
            voice=self.config.voice,
        )
```

### 2. 异步回调处理
`AsyncIteratorCallback` 处理来自 TTS 服务的响应 [6](#0-5) ：

```python
class AsyncIteratorCallback(ResultCallback):
    def on_data(self, data: bytes) -> None:
        # 接收音频数据并发送到队列
        asyncio.run_coroutine_threadsafe(
            self._queue.put((False, MESSAGE_TYPE_PCM, data)), self._loop
        )

    def on_complete(self):
        # 发送完成信号
        asyncio.run_coroutine_threadsafe(
            self._queue.put((True, MESSAGE_TYPE_CMD_COMPLETE, None)), self._loop
        )
```

## 配置和参数

### 1. 配置模型
使用 Pydantic 模型进行类型安全的配置管理（从 extension.py 导入可以看出）。

### 2. 参数传递
manifest.json 定义了扩展的 API 契约 [7](#0-6) ：

```json
{
  "api": {
    "property": {
      "properties": {
        "params": {
          "type": "object",
          "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string"},
            "sample_rate": {"type": "int64"},
            "voice": {"type": "string"}
          }
        }
      }
    }
  }
}
```

## 如何接入自己的 TTS 服务

要接入自己的 TTS 服务，你需要：

### 1. 修改客户端实现
创建自己的 TTS 客户端，实现相同的接口：

```python
class YourTTSClient:
    def __init__(self, config: YourTTSConfig, ten_env: AsyncTenEnv, vendor: str):
        # 初始化你的 TTS 服务客户端

    def synthesize_audio(self, text: str, text_input_end: bool):
        # 调用你的 TTS 服务 API

    async def get_audio_data(self):
        # 返回 (done, message_type, data) 元组
```

### 2. 更新配置模型
根据你的 TTS 服务需求修改配置参数。

### 3. 替换客户端导入
在 extension.py 中替换客户端导入和实例化：

```python
from .your_tts import YourTTSClient

# 在 on_init 中
self.client = YourTTSClient(self.config, ten_env, self.vendor())
```

### 4. 保持接口一致性
确保你的客户端实现返回相同的数据格式：
- `MESSAGE_TYPE_PCM`: 音频数据
- `MESSAGE_TYPE_CMD_COMPLETE`: 完成信号
- `MESSAGE_TYPE_CMD_ERROR`: 错误信息

## 测试和验证

扩展包含完整的测试套件，包括：
- 基本功能测试 [8](#0-7)
- 参数传递测试 [9](#0-8)
- 鲁棒性测试 [10](#0-9)

这些测试可以作为你接入自己 TTS 服务时的参考。

## Notes

- 扩展使用异步架构，支持流式音频处理
- 通过队列机制解耦 TTS 请求和音频处理
- 支持请求状态管理和并发处理
- 包含完整的错误处理和指标收集
- 可以通过修改客户端实现来接入不同的 TTS 服务

Wiki pages you might want to explore:
- [TTS Extension Development (TEN-framework/ten-framework)](/wiki/TEN-framework/ten-framework#6.4)

### Citations

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/extension.py (L35-67)
```python
class CosyTTSExtension(AsyncTTS2BaseExtension):
    def __init__(self, name: str) -> None:
        super().__init__(name)

        # TTS client for Cosy TTS service
        self.client: CosyTTSClient | None = None
        # Configuration for TTS settings
        self.config: CosyTTSConfig | None = None
        # Flag indicating if current request is finished
        self.current_request_finished: bool = True
        # ID of the current TTS request being processed
        self.current_request_id: str | None = None
        # Extension name for logging and identification
        self.name: str = name
        # Store PCMWriter instances for different request_ids
        self.recorder_map: dict[str, PCMWriter] = {}
        # Timestamp when TTS request was sent to service
        self.request_start_ts: datetime | None = None
        # Total audio duration for current request in milliseconds
        self.request_total_audio_duration_ms: int | None = None
        # Time to first byte for current request in milliseconds
        self.request_ttfb: int | None = None
        # Total audio bytes received for current request
        self.total_audio_bytes: int = 0
        # Background task for processing audio data
        self.audio_processor_task: asyncio.Task | None = None
        # Flag indicating if the first chunk has been processed
        self.first_chunk: bool = True
        # Count of audio chunks received
        self.chunk_count: int = 0
        # Flag indicating if the first request is being processed
        self.is_first_message_of_request: bool = False

```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/extension.py (L68-130)
```python
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        try:
            await super().on_init(ten_env)
            ten_env.log_debug("on_init")

            if self.config is None:
                config_json, _ = await self.ten_env.get_property_to_json("")
                self.config = CosyTTSConfig.model_validate_json(config_json)
                # Update params from config
                self.config.update_params()
                # Validate params
                self.config.validate_params()

                self.ten_env.log_info(
                    f"config: {self.config.to_str(sensitive_handling=True)}",
                    category=LOG_CATEGORY_KEY_POINT,
                )

            # Initialize Cosy TTS client
            self.client = CosyTTSClient(self.config, ten_env, self.vendor())
            self.client.start()
            self.audio_processor_task = asyncio.create_task(
                self._process_audio_data()
            )
        except Exception as e:
            ten_env.log_error(f"on_init failed: {traceback.format_exc()}")
            error = ModuleError(
                message=str(e),
                module=ModuleType.TTS,
                code=ModuleErrorCode.FATAL_ERROR.value,
                vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
            )
            await self.send_tts_error(
                request_id="",
                error=error,
            )

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)
        ten_env.log_debug("on_start")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        if self.audio_processor_task:
            self.audio_processor_task.cancel()
            try:
                await self.audio_processor_task
            except asyncio.CancelledError:
                ten_env.log_info("Audio processor task cancelled.")
            self.audio_processor_task = None

        if self.client:
            # The new client is stateless, no stop method needed.
            self.client = None

        # Clean up all PCMWriters
        await self._cleanup_all_pcm_writers()

        await super().on_stop(ten_env)
        ten_env.log_debug("on_stop")

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)
        ten_env.log_debug("on_deinit")
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/extension.py (L159-252)
```python
    async def request_tts(self, t: TTSTextInput) -> None:
        """
        Override this method to handle TTS requests.
        This is called when the TTS request is made.
        """
        try:
            self.ten_env.log_info(
                f"KEYPOINT Requesting TTS for text: {t.text}, text_input_end: {t.text_input_end}, request_id: {t.request_id}, current_request_id: {self.current_request_id}"
            )

            if self.client is None:
                self.ten_env.log_error("Client is not initialized")
                return

            # Check if audio processor task is still running, restart if needed
            if (
                self.audio_processor_task is None
                or self.audio_processor_task.done()
            ):
                self.ten_env.log_info(
                    "Audio processor task not running, restarting..."
                )
                self.audio_processor_task = asyncio.create_task(
                    self._process_audio_data()
                )
                self.ten_env.log_info("Audio processor task restarted")

            if t.request_id != self.current_request_id:
                self.ten_env.log_info(
                    f"KEYPOINT New TTS request with ID: {t.request_id}"
                )
                if not self.current_request_finished:
                    self.client.complete()
                    self.current_request_finished = True

                self.current_request_id = t.request_id
                self.current_request_finished = False
                self.total_audio_bytes = 0  # Reset for new request
                self.request_ttfb = None
                self.first_chunk = True
                self.chunk_count = 0
                self.request_start_ts = datetime.now()
                self.is_first_message_of_request = True

                # Manage PCMWriter instances for audio recording
                await self._manage_pcm_writers(t.request_id)

            elif self.current_request_finished:
                error_msg = f"Received a message for a finished request_id '{t.request_id}' with text_input_end={t.text_input_end}."
                self.ten_env.log_error(error_msg)
                return

            # Get audio stream from Cosy TTS
            self.ten_env.log_debug(
                f"send_text_to_tts_server: {t.text} of request_id: {t.request_id}",
                category=LOG_CATEGORY_VENDOR,
            )

            if (
                self.is_first_message_of_request
                and t.text.strip() == ""
                and t.text_input_end
            ):
                self.ten_env.log_info(
                    f"KEYPOINT skip empty text, request_id: {t.request_id}"
                )
                await self._handle_tts_audio_end()
                return

            # Start audio synthesis (returns immediately)
            if t.text.strip() == "":
                self.ten_env.log_info(
                    f"KEYPOINT skip empty text, request_id: {t.request_id}"
                )
            else:
                # Add output characters to metrics
                char_count = len(t.text)
                self.metrics_add_output_characters(char_count)
                self.ten_env.log_info(
                    f"KEYPOINT add output characters to metrics: {char_count}, request_id: {t.request_id}"
                )

                # Start audio synthesis
                self.client.synthesize_audio(t.text, t.text_input_end)
                self.is_first_message_of_request = False

            # Handle text input end
            if t.text_input_end:
                self.ten_env.log_info(
                    f"KEYPOINT finish session for request ID: {t.request_id}, current_request_id: {self.current_request_id}"
                )
                self.client.complete()
                self.current_request_finished = True

```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/extension.py (L297-441)
```python
    async def _process_audio_data(self) -> None:
        """
        Independent audio data process loop.
        This runs in the background and processes audio data from the client.
        Continuously processes data stream for multiple requests.
        done=True only marks end of current request, loop continues for next request.
        Only breaks on errors, reconnection happens on next synthesize_audio call.
        """
        try:
            self.ten_env.log_info("Starting audio process loop")

            while True:  # Continuous loop for processing multiple requests
                try:
                    self.ten_env.log_info(
                        "Waiting for audio data from client..."
                    )
                    # Get audio data from client
                    done, message_type, data = (
                        await self.client.get_audio_data()
                    )

                    self.ten_env.log_info(
                        f"Received done: {done}, message_type: {message_type}, current_request_id: {self.current_request_id}"
                    )

                    # Process PCM audio chunks
                    if message_type == MESSAGE_TYPE_PCM:
                        audio_chunk = data

                        if (
                            audio_chunk is not None
                            and len(audio_chunk) > 0
                            and isinstance(audio_chunk, bytes)
                        ):
                            # Add recv audio chunks to metrics
                            self.metrics_add_recv_audio_chunks(audio_chunk)
                            self.chunk_count += 1
                            self.total_audio_bytes += len(audio_chunk)
                            # Calculate audio duration for this chunk
                            chunk_duration_ms = self._calculate_audio_duration(
                                len(audio_chunk), self.config.sample_rate
                            )
                            self.ten_env.log_debug(
                                f"receive_audio: duration: {chunk_duration_ms}ms of request_id: {self.current_request_id}",
                                category=LOG_CATEGORY_VENDOR,
                            )

                            # Send TTS audio start on first chunk
                            if self.first_chunk:
                                await self._handle_first_audio_chunk()
                                self.first_chunk = False

                            # Write to dump file if enabled
                            await self._write_audio_to_dump_file(audio_chunk)

                            # Send audio data
                            await self.send_tts_audio_data(audio_chunk)
                        else:
                            self.ten_env.log_info(
                                f"Received empty or invalid payload for TTS response, current_request_id: {self.current_request_id}"
                            )
                    elif message_type == MESSAGE_TYPE_CMD_RESULT_GENERATED:
                        if isinstance(data, int):
                            self.metrics_add_input_characters(data)
                    elif message_type == MESSAGE_TYPE_CMD_ERROR:
                        self.ten_env.log_error(
                            f"vendor_error: {data}",
                            category=LOG_CATEGORY_VENDOR,
                        )
                        error = ModuleError(
                            message=str(data),
                            module=ModuleType.TTS,
                            code=ModuleErrorCode.NON_FATAL_ERROR.value,
                            vendor_info=ModuleErrorVendorInfo(
                                vendor=self.vendor()
                            ),
                        )
                        # Only finish request if we've received text_input_end
                        if self.current_request_finished:
                            await self._handle_tts_audio_end(
                                reason=TTSAudioEndReason.ERROR,
                                error=error,
                            )
                        else:
                            # Just send error, request might continue
                            await self.send_tts_error(
                                request_id=self.current_request_id or "",
                                error=error,
                            )

                    elif message_type == MESSAGE_TYPE_CMD_CANCEL:
                        self.ten_env.log_info(
                            f"Received cancel message from client: {data}"
                        )

                    # Handle TTS audio end - current request done, continue for next
                    if done:
                        self.ten_env.log_info(
                            f"Current request done (request_id: {self.current_request_id}), ready for next request"
                        )
                        await self._handle_tts_audio_end()

                except asyncio.CancelledError:
                    self.ten_env.log_info("Audio consumer task was cancelled.")
                    break
                except Exception as e:
                    self.ten_env.log_error(f"Error in audio consumer loop: {e}")
                    self.ten_env.log_error(
                        "Audio consumer loop breaking due to exception"
                    )
                    # Finish request with error if there's an active request
                    if (
                        self.current_request_id
                        and not self.current_request_finished
                    ):
                        error = ModuleError(
                            message=str(e),
                            module=ModuleType.TTS,
                            code=ModuleErrorCode.NON_FATAL_ERROR.value,
                            vendor_info=ModuleErrorVendorInfo(
                                vendor=self.vendor()
                            ),
                        )
                        await self._handle_tts_audio_end(
                            reason=TTSAudioEndReason.ERROR,
                            error=error,
                        )
                        self.current_request_finished = True
                    # Break loop on error, will reconnect on next synthesize_audio
                    break

        except Exception as e:
            self.ten_env.log_error(f"Fatal error in audio consumer: {e}")
            # Finish request with error if there's an active request
            if self.current_request_id and not self.current_request_finished:
                error = ModuleError(
                    message=str(e),
                    module=ModuleType.TTS,
                    code=ModuleErrorCode.NON_FATAL_ERROR.value,
                    vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
                )
                await self._handle_tts_audio_end(
                    reason=TTSAudioEndReason.ERROR, error=error
                )
                self.current_request_finished = True
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/cosy_tts.py (L48-154)
```python
class AsyncIteratorCallback(ResultCallback):
    """Callback class for handling TTS synthesis results asynchronously."""

    def __init__(
        self,
        ten_env: AsyncTenEnv,
        queue: asyncio.Queue[tuple[bool, int, str | bytes | None]],
    ) -> None:
        self.ten_env = ten_env

        self._closed = False
        self._cancelled = False
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def close(self):
        """Close the callback."""
        self._closed = True

    def cancel(self):
        """Cancel the callback, filtering out further audio output."""
        self._cancelled = True
        self.ten_env.log_info(
            "AsyncIteratorCallback cancelled, will filter audio output"
        )

    def on_open(self):
        """Called when WebSocket connection opens."""
        self.ten_env.log_info("WebSocket connection opened for TTS synthesis.")

    def on_complete(self):
        """Called when TTS synthesis completes successfully."""
        self.ten_env.log_info("TTS synthesis task completed successfully.")

        # Send completion signal only if not cancelled
        if not self._cancelled:
            asyncio.run_coroutine_threadsafe(
                self._queue.put((True, MESSAGE_TYPE_CMD_COMPLETE, None)),
                self._loop,
            )

    def on_error(self, message: str):
        """Called when TTS synthesis encounters an error."""
        self.ten_env.log_error(f"TTS synthesis task failed: {message}")

        # Send error signal only if not cancelled
        if not self._cancelled:
            asyncio.run_coroutine_threadsafe(
                self._queue.put((False, MESSAGE_TYPE_CMD_ERROR, message)),
                self._loop,
            )

    def on_close(self):
        """Called when WebSocket connection closes."""
        self.ten_env.log_info("WebSocket connection closed.")
        self.close()

    def on_event(self, message: str) -> None:
        """Called when receiving events from TTS service."""
        if not self._cancelled:
            try:
                event_data = json.loads(message)
                if (
                    event_data.get("header", {}).get("event")
                    == "result-generated"
                ):
                    char_count = (
                        event_data.get("payload", {})
                        .get("usage", {})
                        .get("characters")
                    )
                    if isinstance(char_count, int):
                        asyncio.run_coroutine_threadsafe(
                            self._queue.put(
                                (
                                    False,
                                    MESSAGE_TYPE_CMD_RESULT_GENERATED,
                                    char_count,
                                )
                            ),
                            self._loop,
                        )
            except json.JSONDecodeError:
                self.ten_env.log_error("Failed to decode TTS event JSON")
            except Exception as e:
                self.ten_env.log_error(f"Error processing TTS event: {e}")

    def on_data(self, data: bytes) -> None:
        """Called when receiving audio data from TTS service."""
        if self._closed:
            self.ten_env.log_warn(
                f"Received {len(data)} bytes but connection was closed"
            )
            return

        if self._cancelled:
            self.ten_env.log_debug(
                f"Filtered {len(data)} bytes audio data due to cancellation"
            )
            return

        self.ten_env.log_info(f"Received audio data: {len(data)} bytes")
        # Send audio data to queue
        asyncio.run_coroutine_threadsafe(
            self._queue.put((False, MESSAGE_TYPE_PCM, data)), self._loop
        )

```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/cosy_tts.py (L156-198)
```python
class CosyTTSClient:
    """Client for Cosy TTS service using dashscope."""

    def __init__(
        self,
        config: CosyTTSConfig,
        ten_env: AsyncTenEnv,
        vendor: str,
    ):
        # Configuration and environment
        self.config = config
        self.ten_env = ten_env
        self.vendor = vendor

        # TTS synthesizer
        self._callback: AsyncIteratorCallback | None = None
        self.synthesizer: SpeechSynthesizer | None = None

        # Communication queue for audio data
        self._receive_queue: asyncio.Queue[
            tuple[bool, int, str | bytes | None]
        ] = asyncio.Queue()

        # Set dashscope API key
        dashscope.api_key = config.api_key

    def start(self) -> None:
        """Start the TTS client and initialize components."""

        # Initialize audio data queue
        self._callback = AsyncIteratorCallback(
            self.ten_env, self._receive_queue
        )

        # Create synthesizer with configuration
        self.synthesizer = SpeechSynthesizer(
            callback=self._callback,
            format=self._get_audio_format(),
            model=self.config.model,
            voice=self.config.voice,
        )

        self.ten_env.log_info("Cosy TTS client started successfully")
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/manifest.json (L28-55)
```json
  "api": {
    "interface": [
      {
        "import_uri": "../../system/ten_ai_base/api/tts-interface.json"
      }
    ],
    "property": {
      "properties": {
        "params": {
          "type": "object",
          "properties": {
            "api_key": {
              "type": "string"
            },
            "model": {
              "type": "string"
            },
            "sample_rate": {
              "type": "int64"
            },
            "voice": {
              "type": "string"
            }
          }
        }
      }
    }
  }
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/tests/test_metrics.py (L76-149)
```python
@patch("cosy_tts_python_local.extension.CosyTTSClient")
def test_ttfb_metric_is_sent(MockCosyTTSClient):
    """
    Tests that a TTFB (Time To First Byte) metric is correctly sent after
    receiving the first audio chunk from the TTS service.
    """
    print("Starting test_ttfb_metric_is_sent with mock...")

    # --- Mock Configuration ---
    mock_instance = MockCosyTTSClient.return_value
    mock_instance.synthesize_audio = AsyncMock()

    # Create state to hold the queue and task
    stream_state = {"queue": None, "task": None}

    async def get_audio_data():
        """Simulate async streaming data from queue"""
        # Lazy initialization: create queue and start producer on first call
        if stream_state["queue"] is None:
            stream_state["queue"] = asyncio.Queue()

            async def simulate_audio_stream():
                """Simulate TTS service sending data asynchronously"""
                queue = stream_state["queue"]
                # Delay to simulate network latency and TTS processing time
                await asyncio.sleep(0.25)  # 250ms TTFB

                # Send first audio chunk
                await queue.put((False, MESSAGE_TYPE_PCM, b"\x11\x22\x33"))

                # Simulate more chunks arriving
                await asyncio.sleep(0.05)
                await queue.put((False, MESSAGE_TYPE_PCM, b"\x44\x55\x66"))

                await asyncio.sleep(0.05)
                await queue.put((False, MESSAGE_TYPE_PCM, b"\x77\x88\x99"))

                # Send completion signal
                await asyncio.sleep(0.05)
                await queue.put((True, MESSAGE_TYPE_CMD_COMPLETE, None))

            # Start producer task in background
            stream_state["task"] = asyncio.create_task(simulate_audio_stream())

        return await stream_state["queue"].get()

    mock_instance.get_audio_data.side_effect = get_audio_data

    # --- Test Setup ---
    # A minimal config is needed for the extension to initialize correctly.
    metrics_config = {
        "params": {
            "api_key": "a_valid_key",
        }
    }
    tester = ExtensionTesterMetrics()
    tester.set_test_mode_single("cosy_tts_python_local", json.dumps(metrics_config))

    print("Running TTFB metrics test...")
    tester.run()
    print("TTFB metrics test completed.")

    # --- Assertions ---
    assert tester.audio_frame_received, "Did not receive any audio frame."
    assert tester.audio_end_received, "Did not receive the tts_audio_end event."
    assert tester.ttfb_received, "TTFB metric was not received."

    # Check if the TTFB value is reasonable. It should be around 250ms with the delay
    # we introduced. Allow 50ms margin for timing variations and system scheduling.
    assert (
        tester.ttfb_value >= 200
    ), f"Expected TTFB to be >= 200ms, but got {tester.ttfb_value}ms."

    print(f"✅ TTFB metric test passed. Received TTFB: {tester.ttfb_value}ms.")
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/tests/test_params.py (L50-127)
```python
@patch("cosy_tts_python_local.extension.CosyTTSClient")
def test_params_passthrough(MockCosyTTSClient):
    """
    Tests that custom parameters passed in the configuration are correctly
    forwarded to the CosyTTSClient client constructor.
    """
    print("Starting test_params_passthrough with mock...")

    # --- Mock Setup ---
    # Create a mock instance with properly configured async methods
    mock_instance = MockCosyTTSClient.return_value
    mock_instance.synthesize_audio = AsyncMock()

    # Create state to hold the queue and task
    stream_state = {"queue": None, "task": None}

    async def get_audio_data():
        """Simulate async streaming data from queue"""
        # Lazy initialization: create queue and start producer on first call
        if stream_state["queue"] is None:
            stream_state["queue"] = asyncio.Queue()

            async def simulate_audio_stream():
                """Simulate TTS service completing immediately"""
                queue = stream_state["queue"]
                await asyncio.sleep(
                    0.01
                )  # Small delay to ensure proper initialization
                await queue.put((True, MESSAGE_TYPE_CMD_COMPLETE, None))

            # Start producer task in background
            stream_state["task"] = asyncio.create_task(simulate_audio_stream())

        return await stream_state["queue"].get()

    mock_instance.get_audio_data.side_effect = get_audio_data

    # --- Test Setup ---
    # Define a configuration with custom, arbitrary parameters inside 'params'.
    # These are the parameters we expect to be "passed through".
    passthrough_params = {
        "api_key": "a_valid_key",
        "model": "cosyvoice-v1",
        "sample_rate": 16000,
        "voice": "longxiaochun",
    }
    passthrough_config = {
        "params": passthrough_params,
    }

    tester = ExtensionTesterForPassthrough()
    tester.set_test_mode_single(
        "cosy_tts_python_local", json.dumps(passthrough_config)
    )

    print("Running passthrough test...")
    tester.run()
    print("Passthrough test completed.")

    # --- Assertions ---
    # Check that the CosyTTSClient client was instantiated exactly once.
    MockCosyTTSClient.assert_called_once()

    # Get the arguments that the mock was called with.
    # The constructor signature is (self, config, ten_env, vendor),
    # so we inspect the 'config' object at index 1 of the call arguments.
    call_args, call_kwargs = MockCosyTTSClient.call_args
    called_config = call_args[0]

    # Verify that the 'params' dictionary in the config object passed to the
    # client constructor is identical to the one we defined in our test config.
    assert (
        called_config.params == passthrough_params
    ), f"Expected params to be {passthrough_params}, but got {called_config.params}"

    print("✅ Params passthrough test passed successfully.")
    print(f"✅ Verified params: {called_config.params}")
```

**File:** ai_agents/agents/ten_packages/extension/cosy_tts_python_local/tests/test_robustness.py (L21-87)
```python
# ================ test reconnect after connection drop(robustness) ================
class ExtensionTesterRobustness(ExtensionTester):
    def __init__(self):
        super().__init__()
        self.first_request_error: Optional[dict[str, Any]] = None
        self.second_request_successful = False
        self.ten_env: Optional[TenEnvTester] = None

    def on_start(self, ten_env_tester: TenEnvTester) -> None:
        """Called when test starts, sends the first TTS request."""
        self.ten_env = ten_env_tester
        ten_env_tester.log_info(
            "Robustness test started, sending first TTS request."
        )

        # First request, expected to fail
        tts_input_1 = TTSTextInput(
            request_id="tts_request_to_fail",
            text="This request will trigger a simulated connection drop.",
        )
        data = Data.create("tts_text_input")
        data.set_property_from_json(None, tts_input_1.model_dump_json())
        ten_env_tester.send_data(data)
        ten_env_tester.on_start_done()

    def send_second_request(self):
        """Sends the second TTS request to verify reconnection."""
        if self.ten_env is None:
            print("Error: ten_env is not initialized.")
            return
        self.ten_env.log_info(
            "Sending second TTS request to verify reconnection."
        )
        tts_input_2 = TTSTextInput(
            request_id="tts_request_to_succeed",
            text="This request should succeed after reconnection.",
        )
        data = Data.create("tts_text_input")
        data.set_property_from_json(None, tts_input_2.model_dump_json())
        self.ten_env.send_data(data)

    def on_data(self, ten_env: TenEnvTester, data) -> None:
        name = data.get_name()
        json_str, _ = data.get_property_to_json(None)
        if not json_str:
            # Not all events have a JSON payload (e.g., tts_audio_start)
            return
        payload = json.loads(json_str)

        if name == "error" and payload.get("id") == "tts_request_to_fail":
            ten_env.log_info(
                f"Received expected error for the first request: {payload}"
            )
            self.first_request_error = payload
            # After receiving the error for the first request, immediately send the second one.
            self.send_second_request()

        elif (
            name == "tts_audio_end"
            and payload.get("request_id") == "tts_request_to_succeed"
        ):
            ten_env.log_info(
                "Received tts_audio_end for the second request. Test successful."
            )
            self.second_request_successful = True
            # We can now safely stop the test.
            ten_env.stop_test()
```
