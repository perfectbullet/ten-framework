# 阿里云 ASR 大模型扩展 - AI 编码代理使用指南

## 项目概述
本项目是一个**TEN 框架扩展**，提供实时语音识别（ASR）功能，支持**双后端架构**：
- **Dashscope（阿里云）** - 基于阿里云大模型（灵积平台）的云端 ASR 服务
- **FunASR（本地服务器）** - 基于自托管 FunASR WebSocket 服务器的本地 ASR

扩展间通过异步消息传递在更大的多智能体 AI 框架中进行通信。

## 架构与核心模式

### 双后端架构
- **后端选择**：通过配置属性 `asr_backend` 指定（"dashscope" 或 "funasr"）
- **统一接口**：两个后端均实现兼容的 `Recognition`、`RecognitionCallback`、`RecognitionResult` 接口
- **FunASR 适配器**（`funasr_adapter.py`）：封装 FunASR WebSocket 客户端以匹配 Dashscope 的 API 接口
- **条件实例化**：`start_connection()` 根据配置分支到 `_start_dashscope_connection()` 或 `_start_funasr_connection()`

### TEN 框架扩展模式
- 扩展需继承自 `ten_ai_base.asr` 中的 `AsyncASRBaseExtension` 类
- 生命周期流程：`on_init` → `start_connection` → `send_audio` 循环 → `finalize` → `stop_connection` → `on_deinit`
- 必须实现的方法：`vendor()`、`buffer_strategy()`、`input_audio_sample_rate()`、`send_audio()`、`is_connected()`
- 使用 `AsyncTenEnv` 进行日志输出，支持日志分类：`LOG_CATEGORY_VENDOR`（厂商相关）、`LOG_CATEGORY_KEY_POINT`（关键节点）

### 回调线程模型（关键）
- **Dashscope**：SDK 回调运行在**厂商线程**，而非 asyncio 事件循环线程
- **FunASR**：WebSocket 接收线程直接调用回调
- 两者均通过 `asyncio.run_coroutine_threadsafe()` 实现厂商/WebSocket 线程与扩展异步循环的桥接
- `AliyunRecognitionCallback`（Dashscope）和 `FunASRCallbackAdapter`（FunASR）均在 `__init__` 中捕获 `asyncio.get_event_loop()`
- **禁止**从回调中直接调用扩展方法——必须使用 `run_coroutine_threadsafe` 进行线程安全调用

### FunASR 消息格式适配
- **中间结果**：`{'is_final': False, 'mode': '2pass-online', 'text': '...', 'wav_name': 'default'}`
- **最终结果**：`{'is_final': True, 'mode': '2pass-offline', 'stamp_sents': [...], 'text': '...', 'timestamp': '...', 'wav_name': 'default'}`
- `FunASRRecognitionResult._build_output()` 将消息转换为与 Dashscope 兼容的结构，包含 `begin_time`、`end_time`、`words[]`
- 从 `stamp_sents[0]['ts_list']` 提取词级时间戳（解决 Dashscope 的 `words[]` 为空的限制）

### 音频时间轴管理
- 跟踪累计音频时长，将厂商相对时间戳映射为绝对时间轴
- `sent_user_audio_duration_ms_before_last_reset` 字段累计重连前后的音频时长
- 音频时长计算公式：`字节长度 / (采样率/1000 * 2)`（默认假设 16 位单声道 PCM 格式）
- 重连时（`on_asr_open` 事件），通过将历史时长累加到 `sent_user_audio_duration_ms_before_last_reset` 保留原有时间轴

### 结束识别模式
支持两种识别结束模式：
1. **`disconnect`**：立即调用 `recognition.stop()` 终止识别
2. **`mute_pkg`**（默认）：发送 `mute_pkg_duration_ms` 时长的静音 PCM 数据（`\x00` 字节），触发厂商返回最终识别结果

### 重连策略
- `ReconnectManager` 实现指数退避重连：300ms → 600ms → 1.2s → 2.4s → 4.8s（最多 5 次尝试）
- 当 `self.stopped == False` 时，若发生意外 `on_asr_close` 事件则触发重连
- 重连成功标记当前在首次收到 `on_asr_event`（识别结果）时设置，确认完整连接周期

## 配置说明

### 后端选择
```python
asr_backend: str = "dashscope"  # "dashscope"（云端）或 "funasr"（本地）
```

### Dashscope（云端）配置
```python
api_key: str  # 必需，通过 ${env:ALIYUN_ASR_BIGMODEL_API_KEY|} 加载
model: str = "paraformer-realtime-v2"  # 默认 ASR 模型
language_hints: List[str] = ["en"]
finalize_mode: str = "mute_pkg"  # 支持 "disconnect" 或 "mute_pkg"
max_sentence_silence: int = 200  # 句子最大静音时长（单位：毫秒，范围 200-6000）
mute_pkg_duration_ms: int = 1000  # 静音包时长，必须大于 max_sentence_silence
vocabulary_list: List[Dict]  # 自定义热词列表
```

### FunASR（本地服务器）配置
```python
funasr_host: str = "127.0.0.1"
funasr_port: str = "10095"
funasr_is_ssl: bool = False  # 使用 WSS (True) 或 WS (False)
funasr_chunk_size: str = "5,10,5"  # 分块大小参数
funasr_chunk_interval: int = 10  # 分块间隔（毫秒）
funasr_mode: str = "2pass"  # 识别模式："2pass"、"offline" 或 "online"
funasr_hotwords: str = ""  # 热词格式："词1 权重\n词2 权重"
funasr_itn: bool = True  # 逆文本规范化
```

### 通用配置
```python
sample_rate: int = 16000  # 采样率
dump: bool = False  # 保存 PCM 数据到 /tmp/aliyun_asr_bigmodel_in.pcm
```
`AliyunASRBigmodelConfig.update(params)` 方法将 `params` 字典合并到配置中——用于覆盖 `property.json` 中的默认值

## 开发工作流

### 运行测试
```bash
# 从扩展根目录执行
export PYTHONPATH=.ten/app:.ten/app/ten_packages/system/ten_runtime_python/lib:.ten/app/ten_packages/system/ten_runtime_python/interface:.ten/app/ten_packages/system/ten_ai_base/interface:$PYTHONPATH
pytest -s tests/
```

**测试结构**：
- `conftest.py` - 会话级 `FakeApp` 提供测试所需的 TEN 运行时上下文
- `mock.py` - 模拟 `Recognition` 类，避免真实厂商调用，支持单元测试
- 通过 `ten_runtime` 中的 `AsyncExtensionTester` 和 `AsyncTenEnvTester` 测试扩展
- 测试用例发送 `AudioFrame` 数据块，验证 `ASRResult` 数据结构的正确性

### 新增功能流程
1. **音频处理相关修改**：更新 `send_audio()` 方法及时间轴计算逻辑
2. **新增厂商参数**：
   - Dashscope：在 `AliyunASRBigmodelConfig` 中添加参数，同步更新 `_start_dashscope_connection()` 中 `DashscopeRecognition()` 的实例化代码
   - FunASR：添加配置参数，更新 `_start_funasr_connection()` 中 `FunASRRecognition()` 的实例化代码
3. **回调处理**：在回调适配器中添加处理器，通过 `run_coroutine_threadsafe` 转发至扩展
4. **后端切换**：使用 `asr_backend="dashscope"` 和 `asr_backend="funasr"` 配置进行测试

### 调试技巧
- 在配置中设置 `dump: true`，可将输入的 PCM 数据保存至 `/tmp/aliyun_asr_bigmodel_in.pcm`
- 查看 `LOG_CATEGORY_VENDOR` 日志获取 SDK 级别的事件信息
- 监控 `sent_user_audio_duration_ms_before_last_reset` 排查时间轴相关问题
- 发送音频前需验证 `is_connected()` 返回 `True`（确保连接已建立）

## 通用模式

### 错误处理
```python
# 非致命错误（厂商侧问题，可重试）
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.NON_FATAL_ERROR.value, message=msg),
    ModuleErrorVendorInfo(vendor=self.vendor(), code=vendor_code, message=vendor_msg)
)

# 致命错误（API 密钥缺失、配置无效等）
await self.send_asr_error(
    ModuleError(module=MODULE_NAME_ASR, code=ModuleErrorCode.FATAL_ERROR.value, message=msg)
)
```

### 敏感数据日志
日志输出时必须使用 `config.to_json(sensitive_handling=True)`，通过 `ten_ai_base.utils.encrypt()` 加密 API 密钥等敏感信息

### AudioFrame 缓冲区管理
```python
buf = frame.lock_buf()
try:
    audio_data = bytes(buf)
    # ... 处理 audio_data ...
finally:
    frame.unlock_buf(buf)  # 无论是否发生异常，必须解锁
```

## 已知限制与待办事项
来自 `代码解读.md` 的记录：
- **词级时间戳（Dashscope）**：`ASRResult.words` 始终为空；FunASR 提供从 `stamp_sents[0]['ts_list']` 填充的 `words[]`
- **立体声音频**：时间轴计算默认假设为单声道（2 字节/采样点）；立体声需按 4 字节/采样点处理
- **重连成功标记**：当前在首次触发 `on_asr_event` 时标记；可迁移至 `on_asr_open` 事件中，以实现更早的反馈
- **FunASR 词汇表格式**：Dashscope 使用 `List[Dict]` 而 FunASR 使用字符串格式 `"词1 权重\n词2 权重"`——共享配置时需要转换

## 依赖项
- `dashscope==1.24.1` - 阿里云大模型 SDK
- `websocket-client` - FunASR 的 WebSocket 客户端
- `pydantic` - 配置验证工具
- TEN 框架包：`ten_runtime_python`、`ten_ai_base`（在 `manifest.json` 中定义）

---
