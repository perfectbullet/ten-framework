# CLAUDE.md

本文档为 Claude Code (claude.ai/code) 在处理本仓库代码时提供指导。

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
 
## TMAN 工具

`tman` 是 TEN 包管理器，用于：
- `tman install` - 从 manifest.json 安装扩展依赖
- `tman run start` - 运行 tenapp
- `tman designer` - 启动 TMAN Designer（可视化图编辑器）
 