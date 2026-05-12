# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

TEN Framework - 实时对话 AI Agent 框架，支持语音、视频和多模态能力。

开发工作集中在 `/ai_agents`，包括 Python 扩展、Go API 服务器和前端 UI。

## Audio Pipeline

音频流经以下扩展链路，在 `property.json` 的 `connections` 中定义：

```
agora_rtc ──(pcm_frame)──→ streamid_adapter ──(pcm_frame)──→ vad ──(pcm_frame)──→ stt (ASR)
                                                                   │
                                                              start_of_sentence
                                                              end_of_sentence
                                                                   │
                                                                   ▼
                                                            main_control ──(asr_finalize)──→ stt
                                                                │   ▲
                                                        asr_result  │   text
                                                                ▼   │
                                                                llm (LLM)
                                                                │
                                                            text (streaming)
                                                                ▼
                                                              tts (TTS) ──(pcm_frame)──→ agora_rtc
```

关键协作机制：
- **VAD 门控**：只在检测到语音活动时透传 PCM 帧给 ASR，静音帧丢弃
- **end_of_sentence → asr_finalize**：VAD 检测到语音结束后，main_control 向 ASR 发 finalize，触发最终识别结果
- **中断机制**：用户说话时 main_control 可中断正在进行的 LLM/TTS

## Architecture Overview

```
ai_agents/
├── agents/
│   ├── ten_packages/extension/      # Python 扩展
│   │   ├── aliyun_asr_bigmodel_local_python  # ASR（阿里云 + FunASR）
│   │   ├── cosy_tts_python_local             # TTS（CosyTTS）
│   │   ├── openai_llm2_python                # LLM（OpenAI 兼容接口）
│   │   ├── silero_vad_python                 # VAD（FSMN）
│   │   ├── ten_vad_python                    # VAD（TEN）
│   │   ├── message_collector2                # 消息收集
│   │   └── streamid_adapter                  # 流 ID 适配
│   └── examples/voice-assistant/    # 主力示例应用
│       └── tenapp/                  # 图配置（manifest.json + property.json）
│           └── ten_packages/extension/main_python/  # 主控扩展（对话管理、中断、ASR 结果处理）
├── server/                          # Go API 服务器（Gin）
└── .env                             # 环境变量
```

## Build & Run

```bash
# 进入开发容器
cd ai_agents && docker compose exec -it ten_agent_dev bash

# 容器内：安装依赖并运行
cd agents/examples/voice-assistant
export LOG_PATH=/var/log
task install    # tman install + python deps + go build API server
task run        # 启动 API server（run-api-server），自动管理 worker 进程

# 也可单独运行 tenapp（不含 API server）
task run-tenapp  # tman run start

# 后台运行 + 查看日志
nohup task run > info.log 2>&1 &
tail -n1 -f info.log
```

## Common Commands

```bash
# 从 ai_agents/ 目录执行
task lint                          # Lint 所有 Python 扩展
task lint-extension EXTENSION=cosy_tts_python_local  # Lint 单个扩展
task format                        # black 格式化（line-length 80）
task test                          # 运行所有测试（extensions + server）
task test-extension EXTENSION=agents/ten_packages/extension/cosy_tts_python_local
task test-server                   # Go server 测试
task asr-guarder-test              # ASR 集成测试
task tts-guarder-test EXTENSION=cosy_tts_python_local  # TTS 集成测试
```

## Extension Structure

每个 Python 扩展遵循统一结构：

```
extension_name/
├── addon.py           # 入口，@register_addon_as_extension 注册
├── extension.py       # 主类，继承 ten_ai_base 的基类
├── manifest.json      # 元数据、依赖、API 接口定义
├── property.json      # 默认属性（配置 schema）
├── requirements.txt   # Python 依赖
└── tests/             # 独立测试
```

**addon.py 注册模式：**
```python
@register_addon_as_extension("extension_name")
class MyExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        from .extension import MyExtension
        ten_env.on_create_instance_done(MyExtension(name), context)
```

**基类**（`ten_ai_base` 系统包，安装后在 `.ten/` 下）：
- `AsyncASRBaseExtension` — ASR 扩展，管理音频帧队列、连接生命周期、finalize 流程
- `AsyncTTS2BaseExtension` — TTS 扩展
- `AsyncLLMBaseExtension` — LLM 扩展

## Graph Configuration

扩展通过 `property.json` 中的图定义连接。图定义了节点（扩展）、属性和消息连接。

- 环境变量替换：`${env:VAR_NAME|default}`
- 本地扩展依赖：`{"path": "../../../ten_packages/extension/cosy_tts_python_local"}`
- 音频帧连接：`audio_frame` 段定义 pcm_frame 的 source/dest
- 命令连接：`cmd` 段定义 command 的路由
- 数据连接：`data` 段定义 data message 的路由

## API Server

Go 服务器（`ai_agents/server/`）提供 REST API：
- `POST /start` — 为频道创建 worker
- `POST /stop` — 停止 worker
- `POST /token/generate` — 生成 Agora RTC token
- `GET /graphs` — 列出可用图
- `GET /health` — 健康检查

Worker 以子进程方式运行（`/app/agents/bin/start`），按频道名管理。

## Message Types

扩展间通信：
- **Data messages** — 结构化数据（asr_result, text 等）
- **Command messages** — 控制命令（on_user_joined, start_of_sentence, end_of_sentence 等）
- **Audio frames** — PCM 音频流（16kHz, 16-bit, mono）
- **Video frames** — 视频数据

## Language Tooling

- **Python**: `black`（line-length 80），`pyright` 类型检查。PYTHONPATH 需包含 `ten_runtime_python/lib`、`ten_runtime_python/interface`、`ten_ai_base/interface`
- **Go**: `go test -v ./...`（在 `server/` 目录下）
- **TypeScript**: `npm run lint` / `npm run format`（Biome）

## Environment Variables

在 `ai_agents/agents/examples/voice-assistant/.env` 中配置（docker-compose 的 env_file）。

关键变量：
- `AGORA_APP_ID`（32 字符，启动时校验）、`AGORA_APP_CERTIFICATE`
- `ALIYUN_ASR_BIGMODEL_API_KEY`、FunASR 连接参数
- `COSY_TTS_API_KEY`
- `OPENAI_API_KEY`、`OPENAI_MODEL`（或兼容接口的 base_url）
- `LOG_PATH`、`LOG_STDOUT`、`SERVER_PORT`、`WORKERS_MAX`

完整列表见 `ai_agents/.env.example`。

## Auto-Generated Files（不要修改）

- `manifest-lock.json` — tman 依赖锁
- `BUILD.gn` — 构建配置
- `.ten/` — 运行时生成文件（含 ten_ai_base、ten_runtime_python 等系统包）
- `bin/main`、`bin/worker` — 编译产物
