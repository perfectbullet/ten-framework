# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **TEN Framework** monorepo - an open-source framework for building real-time conversational AI agents with voice, video, and multimodal capabilities.

Two main components:
1. **Core Framework** (`/core`, `/packages`) - Runtime engine written in Rust, Go, and C++
2. **AI Agents** (`/ai_agents`) - Pre-built extensions, examples, and server for AI agents

Most day-to-day development happens in `/ai_agents`.

## Build System

Uses `task` (go-task/task) as the task runner and **GN** (Generate Ninja) as the build system for the core framework.

```bash
# Core framework (from repo root)
task gen-tman          # Generate build files (includes tman package manager)
task build             # Build the core framework
task build-tman        # Build only tman
task clean             # rm -rf out/

# AI agents (from ai_agents/)
task lint              # Lint all Python extensions
task lint-extension EXTENSION=cosy_tts_python   # Lint single extension
task format            # Format Python code with black (line-length 80)
task test              # Run all tests (extensions + server)
task test-extension EXTENSION=agents/ten_packages/extension/cosy_tts_python  # Test single extension
task test-extension-no-install EXTENSION=...     # Test without reinstalling deps
task test-server       # Go tests for server only
task asr-guarder-test  # ASR integration tests
task tts-guarder-test  # TTS integration tests
```

## Architecture Overview

```
ten-framework/
├── core/              # Core runtime engine (Rust/Go/C++)
├── packages/          # Core packages (addon loaders, extensions, protocols)
├── ai_agents/
│   ├── agents/
│   │   ├── ten_packages/extension/   # ~36 Python extensions (ASR, TTS, LLM, tools)
│   │   ├── ten_packages/system/      # System packages (ten_runtime_python, ten_ai_base)
│   │   └── examples/voice-assistant/ # Primary example agent
│   ├── server/        # Go API server (Gin) - manages agent workers
│   └── playground/    # Next.js frontend UI
├── tests/             # Test framework
└── tools/             # Development tools
```

## AI Agents Development

### Dev Container

Development runs inside a Docker container (`ten_agent_dev`):

```bash
cd ai_agents
docker compose up -d
docker exec -it ten_agent_dev bash
```

The container mounts `ai_agents/` at `/app` and uses `agents/examples/voice-assistant/.env` for environment variables. All debugging must happen inside the container.

### Running the Agent (inside container)

```bash
cd agents/examples/voice-assistant
export LOG_PATH=/var/log
task install           # Install deps (tman + python deps + build API server)
task run               # Runs the API server (bin/api -tenapp_dir=...)
```

The API server spawns `tman run start` worker processes for each channel. Logs go to `$LOG_PATH` or stdout.

### Extension Structure

Every Python extension follows this pattern:

```
extension_name/
├── addon.py           # Entry point - registers extension with @register_addon_as_extension
├── extension.py       # Main extension class (inherits from AsyncTenEnv base)
├── manifest.json      # Extension metadata, dependencies, API interface
├── property.json      # Default properties (config schema)
├── requirements.txt   # Python dependencies
└── tests/             # Standalone tests
```

**addon.py pattern** (entry point that the runtime discovers):
```python
@register_addon_as_extension("extension_name")
class MyExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        from .extension import MyExtension
        ten_env.on_create_instance_done(MyExtension(name), context)
```

Base classes for extensions live in `ten_ai_base` system package:
- `AsyncTTS2BaseExtension` - TTS extensions
- `AsyncASRBaseExtension` - ASR extensions
- `AsyncLLMBaseExtension` - LLM extensions

### Graph Configuration

Extensions are wired together via `property.json` in the app's `tenapp/` directory. The graph defines nodes (extensions), their properties, and connections (how messages flow between them). Environment variable substitution uses `${env:VAR_NAME|default}` syntax.

Example dependency declaration in `manifest.json`:
```json
{
  "type": "extension",
  "name": "cosy_tts_python",
  "dependencies": [
    {"type": "system", "name": "ten_runtime_python", "version": "0.11"},
    {"type": "system", "name": "ten_ai_base", "version": "0.7"}
  ]
}
```

Path-based dependencies (for local dev) in app's `manifest.json`:
```json
{"path": "../../../ten_packages/extension/cosy_tts_python"}
```

### API Server

The Go server (`ai_agents/server/`) exposes REST endpoints for agent lifecycle:
- `POST /start` - Spawn a worker for a channel
- `POST /stop` - Stop a worker
- `POST /token/generate` - Generate Agora RTC token
- `GET /graphs` - List available graphs from property.json
- `GET /health` - Health check

Workers run as child processes (`/app/agents/bin/start`) managed per channel name.

### Message Types

Extensions communicate via:
- **Data messages** - Structured data (asr_result, text, etc.)
- **Command messages** - Control commands (on_user_joined, tool_register, etc.)
- **Audio frames** - PCM audio streams
- **Video frames** - Video data

## Git-Ignored Auto-Generated Files

Do NOT modify these - they are generated by the build system:
- `out/` - Build output
- `.gn`, `.gnfiles/` - GN build system files
- `manifest-lock.json` - tman dependency lock
- `BUILD.gn` - Build configuration
- `.ten/` - Runtime generated files
- `bin/main`, `bin/worker` - Compiled binaries
- `compile_commands.json` - LSP support

## Language Tooling

- **Python**: `black` (line-length 80), `pyright` for type checking. PYTHONPATH must include `ten_runtime_python/lib`, `ten_runtime_python/interface`, and `ten_ai_base/interface`
- **Go**: `go test ./...` for server tests
- **TypeScript/JavaScript**: `npm run lint` / `npm run format` uses Biome (root package.json)
- **Rust**: Core runtime, build via `task build`
- **C++**: Core runtime API, uses `.clang-format` / `.clang-tidy`

## Environment Variables

Required for running AI agents. Set in `ai_agents/agents/examples/voice-assistant/.env` (the docker-compose env_file source). See `ai_agents/.env.example` for the complete list. Key ones:

- `AGORA_APP_ID` (32 chars, validated at server startup), `AGORA_APP_CERTIFICATE`
- `LOG_PATH`, `LOG_STDOUT`, `SERVER_PORT`, `WORKERS_MAX`
- API keys per extension (e.g., `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_TTS_KEY`)
