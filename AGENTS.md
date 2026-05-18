# AGENTS.md

This file provides guidance to Codex and other agentic coding tools when working with this repository.

## Repository Summary

TEN Framework is a monorepo for real-time conversational AI systems. The repository has two main centers of gravity:

- `core/`, `packages/`, `tools/`, and `tests/` implement the underlying TEN runtime, manager, protocols, loaders, and test infrastructure.
- `ai_agents/` contains the most active product-facing work: agent examples, Python extensions, a Go API server, frontend playground code, and hardware clients.

If a task mentions voice assistant behavior, ASR/VAD/TTS/LLM wiring, runtime graph config, or agent startup, start in `ai_agents/`.

## Where To Start

- Root overview: `README.md`
- Existing Claude-oriented notes: `CLAUDE.md`
- AI agents subtree guide: `ai_agents/AGENTS.md`
- Main example app: `ai_agents/agents/examples/voice-assistant`
- Main runtime graph: `ai_agents/agents/examples/voice-assistant/tenapp/property.json`
- Main Python control extension: `ai_agents/agents/examples/voice-assistant/tenapp/ten_packages/extension/main_python`
- Agent API server: `ai_agents/server`
- Root task automation for agent extensions: `ai_agents/Taskfile.yml`

## Architecture Snapshot

- `core/`: C/C++ runtime, bindings, internals, and foundational libraries.
- `packages/`: reusable TEN apps, extensions, protocols, and addon loaders.
- `tests/`: smoke, integration, and manager/runtime tests.
- `ai_agents/agents/ten_packages/extension/`: Python-based AI extensions such as ASR, VAD, LLM, and TTS providers.
- `ai_agents/agents/examples/voice-assistant/`: the primary end-to-end example that ties RTC, STT, LLM, and TTS together.
- `ai_agents/server/`: Go HTTP server that starts and manages worker processes for TEN apps.
- `ai_agents/playground/`: frontend workspace used by the agent examples.

## Preferred Workflow

For most user requests in this repo:

1. Check whether the task belongs to the core framework or `ai_agents`.
2. If it touches agent behavior, inspect `ai_agents/AGENTS.md` and the target example's `Taskfile.yml`.
3. Prefer editing source files, not generated output.
4. Verify with the narrowest relevant command.

## High-Value Commands

### Root formatting

```bash
npm run lint
npm run format
```

### AI agents workspace

```bash
cd ai_agents
task lint
task test
task test-server
```

### Voice assistant example

```bash
cd ai_agents/agents/examples/voice-assistant
task install
task run
task run-tenapp
task run-api-server
```

## Important Conventions

- Prefer `rg` and `rg --files` for search.
- Treat `ai_agents/agents/examples/voice-assistant` as the default example unless the task points elsewhere.
- Many runtime behaviors are configured in `manifest.json` and `property.json`, not only in Python or Go code.
- The agent graph is message-driven. Changes to ASR, VAD, LLM, TTS, interrupts, or routing often require reading both code and graph config.

## Generated Or Ignored Files

Do not hand-edit generated or ignored outputs unless the user explicitly asks for that:

- `.ten/`
- `out/`
- `node_modules/`
- `ai_agents/server/bin/`
- `BUILD.gn`
- `compile_commands.json`
- `manifest-lock.json`
- runtime logs, caches, and build artifacts

Also note that this repository's `.gitignore` intentionally ignores some local voice-assistant files, including the main example's `property.json`, so inspect git status carefully before assuming a change is tracked.

## Local Worktree Safety

This repository may contain local-only experiments and ignored customization files. Avoid reverting unrelated changes. The current task should stay scoped to the files it actually needs.

## Practical Heuristics

- If a bug is about request lifecycle, channels, worker startup, or REST endpoints, inspect `ai_agents/server`.
- If a bug is about speech segmentation, end-of-sentence timing, or interruptions, inspect VAD/ASR plus `main_python` and graph connections.
- If a bug is about build, install, or dependency bootstrap, inspect the nearest `Taskfile.yml`, shell scripts under `ai_agents/scripts`, and root build config.
- If a task is unclear at the root level, defer to the deeper guide in `ai_agents/AGENTS.md` for agent-specific work.
