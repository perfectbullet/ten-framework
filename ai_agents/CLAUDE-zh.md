# CLAUDE.md

本文档为 AI 在处理本仓库代码时提供指导。

## 仓库概述

这是 **TEN 框架 AI 代理** 仓库，是一个模块化平台，用于构建具有语音、视频和多模态能力的实时 AI 代理。该框架采用基于图的架构，其中扩展（ASR、LLM、TTS、RTC、工具等）通过 property.json 配置连接，以创建完整的 AI 代理管道。

## 开发指南

### 不要修改 Git 忽略的文件

**重要提示：** 不要修改被 git 忽略的文件——它们是由构建工具自动生成或管理的。

本仓库中常见的自动生成文件（参见 `agents/.gitignore`）：
- `manifest-lock.json` - 由 tman 在依赖解析期间生成
- `compile_commands.json` - 由构建系统生成
- `BUILD.gn` - 生成的构建配置
- `.gn`、`.gnfiles` - 生成的构建系统链接
- `out/` - 构建输出目录
- `.ten/` - TEN 运行时生成的文件
- `bin/main`、`bin/worker` - 编译后的二进制文件
- `.release/` - 发布打包输出
- `*.log` 文件 - 运行时日志
- `build/` 目录 - 构建产物
- `node_modules/` - JavaScript 依赖

进行修改时：
- 专注于源文件：`*.py`、`*.go`、`*.ts`、`*.tsx`、`manifest.json`、`property.json`、`Taskfile.yml`
- 让构建工具重新生成它们的输出文件
- 如果需要修改构建行为，编辑源配置（例如 `Taskfile.yml`、`package.json`）而不是生成的文件

## 核心架构

### 扩展系统

TEN 框架围绕**扩展**构建——提供特定功能（ASR、TTS、LLM、工具等）的模块化组件。扩展通过基于图的消息传递系统进行通信。

**扩展结构：**
- `manifest.json` - 扩展元数据、依赖项和 API 接口定义
- `property.json` - 默认配置和参数（支持 `${env:VAR_NAME}` 语法）
- `addon.py` - 使用 `@register_addon_as_extension` 装饰器的注册类
- `extension.py` - 主要扩展逻辑，继承自 `AsyncASRBaseExtension`、`AsyncTTSBaseExtension` 等基类
- `tests/` - 带有 `bin/start` 脚本的独立测试目录

**基础扩展类：**
- 位于 `agents/ten_packages/system/ten_ai_base/interface/ten_ai_base/`
- 常见基类：`AsyncASRBaseExtension`、`AsyncTTSBaseExtension`、`LLMBaseExtension`
- API 接口定义在 `agents/ten_packages/system/ten_ai_base/api/*.json`

### 基于图的配置

代理通过 `property.json` 中的 **predefined_graphs** 进行配置：

```json
{
  "ten": {
    "predefined_graphs": [{
      "name": "voice_assistant",
      "auto_start": true,
      "graph": {
        "nodes": [
          {"name": "stt", "addon": "deepgram_asr_python", "property": {...}},
          {"name": "llm", "addon": "openai_llm2_python", "property": {...}},
          {"name": "tts", "addon": "elevenlabs_tts2_python", "property": {...}}
        ],
        "connections": [
          {
            "extension": "main_control",
            "data": [{"name": "asr_result", "source": [{"extension": "stt"}]}]
          }
        ]
      }
    }]
  }
}
```

**连接类型：**
- `data` - 数据消息（asr_result、text 等）
- `cmd` - 命令消息（on_user_joined、tool_register 等）
- `audio_frame` - 音频流数据（pcm_frame）
- `video_frame` - 视频流数据

### 仓库结构

```
agents/
├── ten_packages/
│   ├── extension/          # 60 多个扩展（ASR、TTS、LLM、工具等）
│   │   ├── deepgram_asr_python/
│   │   ├── openai_llm2_python/
│   │   ├── elevenlabs_tts2_python/
│   │   └── ...
│   ├── system/             # 核心框架包
│   │   ├── ten_ai_base/    # 基类和 API 接口
│   │   ├── ten_runtime_python/
│   │   └── ten_runtime_go/
│   └── addon_loader/       # 特定语言的插件加载器
├── examples/               # 完整的代理示例
│   ├── voice-assistant/    # 基本语音代理（STT→LLM→TTS）
│   ├── voice-assistant-realtime/  # OpenAI 实时 API
│   ├── voice-assistant-video/     # 视觉能力
│   └── ...
├── integration_tests/
│   ├── asr_guarder/        # ASR 集成测试框架
│   └── tts_guarder/        # TTS 集成测试框架
├── scripts/                # 构建和打包脚本
└── manifest.json           # 应用级清单

server/                     # Go API 服务器
├── main.go                 # 用于代理生命周期的 HTTP 服务器
└── internal/               # 服务器实现

playground/                 # Next.js 前端 UI
└── src/                    # React 组件

esp32-client/              # ESP32 硬件客户端
```

## 开发命令

### 构建与 lint

```bash
# 对所有 Python 扩展进行 lint 检查
task lint

# 对特定扩展进行 lint 检查
task lint-extension EXTENSION=deepgram_asr_python

# 使用 black 格式化 Python 代码
task format

# 检查代码格式
task check
```

### 测试

```bash
# 运行所有测试（服务器 + 扩展）
task test

# 测试特定扩展
task test-extension EXTENSION=agents/ten_packages/extension/elevenlabs_tts_python

# 测试扩展而不重新安装依赖
task test-extension-no-install EXTENSION=agents/ten_packages/extension/elevenlabs_tts_python

# 运行 ASR guarder 集成测试
task asr-guarder-test EXTENSION=azure_asr_python CONFIG_DIR=tests/configs

# 运行 TTS guarder 集成测试
task tts-guarder-test EXTENSION=bytedance_tts_duplex CONFIG_DIR=tests/configs
```

**扩展测试运行器：**
带有 `tests/` 目录的扩展使用独立测试：
- 测试入口点：`tests/bin/start`（shell 脚本）
- 设置 PYTHONPATH 以包含 ten_runtime_python 和 ten_ai_base 接口
- 运行 pytest 或自定义测试 harness
- 需要带有 API 密钥的 `.env` 文件

### 运行示例

每个示例都有自己的 Taskfile.yml：

```bash
# 导航到示例目录
cd agents/examples/voice-assistant

# 安装依赖（前端、服务器、tenapp）
task install

# 运行所有组件（API 服务器、前端、TMAN Designer）
task run

# 运行单个组件
task run-api-server
task run-frontend
task run-gd-server     # TMAN Designer 在端口 49483 上运行
```

**端口：**
- 前端：`http://localhost:3000`
- API 服务器：`http://localhost:8080`
- TMAN Designer：`http://localhost:49483`

### 服务器 API

Go 服务器通过 REST API 管理代理进程：

**POST /start** - 使用图启动代理
```json
{
  "request_id": "uuid",
  "channel_name": "test_channel",
  "user_uid": 176573,
  "graph_name": "voice_assistant",
  "properties": {},
  "timeout": 60
}
```

**POST /stop** - 停止代理
**POST /ping** - 保持代理活跃（如果 timeout != -1）

## Python 开发

### PYTHONPATH 配置

扩展需要特定的 PYTHONPATH 来导入 TEN 运行时和 AI 基础：

```bash
export PYTHONPATH="./agents/ten_packages/system/ten_runtime_python/lib:./agents/ten_packages/system/ten_runtime_python/interface:./agents/ten_packages/system/ten_ai_base/interface"
```

这在以下位置配置：
- `Taskfile.yml` 任务（lint、test-extension）
- `pyrightconfig.json`（每个示例的 executionEnvironments）
- 扩展测试脚本（`tests/bin/start`）

### 类型检查

Pyright 在 `pyrightconfig.json` 中配置：
- 模式：`basic`
- 关键检查：`reportUnusedCoroutine`、`reportMissingAwait`、`reportUnawaitedAsyncFunctions` = error
- 大多数类型检查被禁用，以适应动态 TEN 运行时 API
- 每个示例有单独的执行环境，以正确解析导入

## 扩展开发模式

### 创建新扩展

1. **继承基类：**
   ```python
   from ten_ai_base.asr import AsyncASRBaseExtension

   class MyASRExtension(AsyncASRBaseExtension):
       async def on_init(self, ten_env: AsyncTenEnv) -> None:
           await super().on_init(ten_env)
           # 从 property.json 加载配置
           config_json, _ = await ten_env.get_property_to_json("")
   ```

2. **注册插件：**
   ```python
   from ten_runtime import Addon, register_addon_as_extension

   @register_addon_as_extension("my_asr_python")
   class MyASRExtensionAddon(Addon):
       def on_create_instance(self, ten: TenEnv, addon_name: str, context) -> None:
           ten.on_create_instance_done(MyASRExtension(addon_name), context)
   ```

3. **在 manifest.json 中定义 API 接口：**
   ```json
   {
     "api": {
       "interface": [
         {"import_uri": "../../system/ten_ai_base/api/asr-interface.json"}
       ]
     }
   }
   ```

### 常见模式

**使用 Pydantic 进行配置：**
扩展通常使用 Pydantic 模型进行配置验证：
```python
from pydantic import BaseModel

class MyConfig(BaseModel):
    api_key: str
    model: str = "default"
```

**环境变量：**
在 property.json 中使用 `${env:VAR_NAME}` 或 `${env:VAR_NAME|}`（带有 fallback）：
```json
{"api_key": "${env:DEEPGRAM_API_KEY}"}
```

**日志类别：**
- `LOG_CATEGORY_KEY_POINT` - 重要的生命周期事件
- `LOG_CATEGORY_VENDOR` - 供应商特定的状态/错误

**消息发送：**
- `await self.send_asr_result(asr_result)`
- `await self.send_asr_error(module_error, vendor_info)`
- `await self.send_asr_finalize_end()`

### 配置和参数处理

**参数字典模式：**
使用基于 HTTP 的服务（TTS、ASR 等）的扩展通常将所有配置存储在 `params` 字典中，该字典会传递给供应商 API。遵循以下模式：

**1. 敏感参数（API 密钥）：**
- 在 property.json 和配置中将 `api_key` 存储在 `params` 字典中
- 在客户端构造函数中提取用于身份验证头
- **仅在创建 HTTP 请求 payload 时**从参数中剥离（不在配置处理期间）

来自 `rime_http_tts` 的示例：
```python
# config.py - 始终将 api_key 保留在 params 中
class RimeTTSConfig(AsyncTTS2HttpConfig):
    params: dict[str, Any] = Field(default_factory=dict)

    def validate(self) -> None:
        if "api_key" not in self.params or not self.params["api_key"]:
            raise ValueError("API 密钥是必需的")

# rime_tts.py - 提取用于头，从 payload 中剥离
class RimeTTSClient(AsyncTTS2HttpClient):
    def __init__(self, config: RimeTTSConfig, ten_env: AsyncTenEnv):
        self.api_key = config.params.get("api_key", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def get(self, text: str, request_id: str):
        # 浅拷贝并在发送前剥离 api_key
        payload = {** self.config.params}
        payload.pop("api_key", None)

        async with self.client.stream("POST", url, json={"text": text, **payload}):
            # ...
```

**2. 参数类型保留：**
- 在 `manifest.json` `api.property.properties` 中正确定义参数类型
- 对于整数参数使用 `"int32"`，对于浮点数使用 `"float64"`，对于字符串使用 `"string"`
- Pydantic 将根据 manifest.json 模式定义强制转换类型

示例：
```json
// manifest.json
"params": {
  "type": "object",
  "properties": {
    "api_key": {"type": "string"},
    "top_p": {"type": "int32"},      // 整数参数
    "temperature": {"type": "float64"},  // 浮点数参数
    "samplingRate": {"type": "int32"}
  }
}
```

**3. update_params() 中的参数转换：**
- 添加供应商所需的参数（例如 `audioFormat`、`segment`）
- 规范化替代键名（例如 `sampling_rate` → `samplingRate`）
- 从黑名单中移除仅内部使用的参数
- 不要在此处剥离 api_key（仅在发出请求时剥离）

示例：
```python
def update_params(self) -> None:
    # 添加必需的参数
    self.params["audioFormat"] = "pcm"
    self.params["segment"] = "immediate"

    # 规范化键
    if "sampling_rate" in self.params:
        self.params["samplingRate"] = int(self.params["sampling_rate"])
        del self.params["sampling_rate"]

    # 移除仅内部使用的参数（不是 api_key）
    blacklist = ["text"]
    for key in blacklist:
        self.params.pop(key, None)
```

**4. 日志中的敏感数据：**
- 实现 `to_str()` 方法来加密敏感字段
- 日志记录前使用 `utils.encrypt()` 处理 api_key

示例：
```python
def to_str(self, sensitive_handling: bool = True) -> str:
    if not sensitive_handling:
        return f"{self}"

    config = copy.deepcopy(self)
    if config.params and "api_key" in config.params:
        config.params["api_key"] = utils.encrypt(config.params["api_key"])
    return f"{config}"
```

### 高级扩展模式

**1. 双向扩展（输入 + 输出）**

扩展可以既从 TEN 图接收又向其发送。这种模式适用于桥接器、代理和传输层。

关键技术：
- 在 `__init__` 中存储 `self.ten_env` 引用，供回调使用
- 实现 `on_audio_frame()` 或 `on_data()` 以从图接收
- 使用回调将外部系统与 TEN 图桥接

示例：
```python
class MyExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.ten_env: AsyncTenEnv = None  # 为回调存储

    async def on_init(self, ten_env: AsyncTenEnv):
        self.ten_env = ten_env  # 保存引用

    async def on_audio_frame(self, ten_env, audio_frame):
        # 从图接收 → 转发到外部系统
        buf = audio_frame.lock_buf()
        pcm_data = bytes(buf)
        audio_frame.unlock_buf(buf)
        self.external_system.send(pcm_data)

    async def _external_callback(self, data):
        # 从外部系统接收 → 发送到图
        audio_frame = AudioFrame.create("pcm_frame")
        # ... 配置帧 ...
        await self.ten_env.send_audio_frame(audio_frame)
```

**2. AudioFrame 创建模式**

创建和发送 AudioFrames 的标准模式：

```python
# 创建帧
audio_frame = AudioFrame.create("pcm_frame")

# 设置属性（顺序很重要 - 在 alloc_buf 之前进行）
audio_frame.set_sample_rate(16000)
audio_frame.set_bytes_per_sample(2)  # 16 位音频
audio_frame.set_number_of_channels(1)  # 单声道
audio_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
audio_frame.set_samples_per_channel(len(pcm_data) // 2)

# 分配并填充缓冲区
audio_frame.alloc_buf(len(pcm_data))
buf = audio_frame.lock_buf()
buf[:] = pcm_data
audio_frame.unlock_buf(buf)

# 发送到图
await ten_env.send_audio_frame(audio_frame)
```

关键点：
- 始终使用 `AudioFrame.create()` 工厂方法（不是 `__init__`）
- 在调用 `alloc_buf()` 之前设置所有属性
- 锁定/解锁缓冲区模式确保线程安全
- 计算样本数：`samples_per_channel = total_bytes / (bytes_per_sample * channels)`

## TMAN 工具

`tman` 是 TEN 包管理器，用于：
- `tman install` - 从 manifest.json 安装扩展依赖
- `tman run start` - 运行 tenapp
- `tman designer` - 启动 TMAN Designer（可视化图编辑器）

## 集成测试

**ASR Guarder**（`agents/integration_tests/asr_guarder/`）：
- 使用音频流测试 ASR 扩展
- 验证重新连接、完成、多语言、指标
- 使用 pytest 夹具和 conftest.py

**TTS Guarder**（`agents/integration_tests/tts_guarder/`）：
- 使用文本输入测试 TTS 扩展
- 验证刷新、边界情况、无效文本处理、指标

两者都使用基于模板的清单生成：
```bash
sed "s/{{extension_name}}/$EXT_NAME/g" manifest-tmpl.json > manifest.json
```

## 环境配置

所需的 `.env` 变量取决于所使用的扩展。常见的有：

**RTC：**
- `AGORA_APP_ID`、`AGORA_APP_CERTIFICATE`

**LLM：**
- `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_API_BASE`
- `AZURE_OPENAI_REALTIME_API_KEY`、`AZURE_OPENAI_REALTIME_BASE_URI`

**ASR：**
- `DEEPGRAM_API_KEY`、`AZURE_ASR_API_KEY`、`AZURE_ASR_REGION`

**TTS：**
- `ELEVENLABS_TTS_KEY`、`AZURE_TTS_KEY`、`AZURE_TTS_REGION`

完整列表参见 `.env.example`。

## 需检查的关键文件

处理以下内容时：
- **新扩展** → 查看 `agents/ten_packages/extension/<similar_extension>/` 以获取模式
- **API 变更** → 查看 `agents/ten_packages/system/ten_ai_base/api/*.json`
- **图配置** → 查看 `agents/examples/*/tenapp/property.json`
- **测试设置** → 查看 `agents/ten_packages/extension/*/tests/bin/start`

## 常见问题

**扩展中的导入错误：**
- 确保 PYTHONPATH 包含 ten_runtime_python 和 ten_ai_base 接口
- 检查示例的 pyrightconfig.json executionEnvironments

**扩展未加载：**
- 验证 manifest.json 依赖项与安装的包匹配
- 检查 addon.py 装饰器名称与 property.json 中的 "addon" 字段匹配
- 在 tenapp 目录中运行 `tman install`

**测试失败：**
- 确保 .env 有必需的 API 密钥
- 检查 tests/bin/start 脚本中的 PYTHONPATH
- 验证 tests/configs/ 目录中的测试配置