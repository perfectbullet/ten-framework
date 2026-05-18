# Workflow: Debug Voice Assistant

Use this when the issue is in the default end-to-end voice assistant flow.

## Primary Scope

- Example root: `ai_agents/agents/examples/voice-assistant`
- Graph config: `ai_agents/agents/examples/voice-assistant/tenapp/property.json`
- Main control extension: `ai_agents/agents/examples/voice-assistant/tenapp/ten_packages/extension/main_python`
- API server: `ai_agents/server`

## Fast Triage

1. Confirm whether the problem is startup, routing, model behavior, or server lifecycle.
2. Read the example `Taskfile.yml` before changing commands or install flow.
3. Inspect both code and graph wiring. In this repository, message routing bugs often live in `property.json`, not only in Python.

## Common Failure Buckets

### App does not start

- Check `ai_agents/agents/examples/voice-assistant/Taskfile.yml`
- Check `ai_agents/server` build and runtime assumptions
- Check required env vars mentioned in the example README

### ASR/VAD/TTS/LLM behavior is wrong

- Inspect node properties and connections in `tenapp/property.json`
- Inspect `main_python/extension.py`
- Inspect the relevant provider extension under `ai_agents/agents/ten_packages/extension`

### Channel or worker lifecycle is wrong

- Inspect `ai_agents/server/internal/worker.go`
- Inspect `ai_agents/server/internal/http_server.go`
- Inspect `ai_agents/server/internal/config.go`

## Verification

Use the narrowest relevant command:

```bash
cd ai_agents/agents/examples/voice-assistant
task run
```

If the issue is server-only:

```bash
cd ai_agents
task test-server
```

If the issue is inside a reusable extension:

```bash
cd ai_agents
task test-extension EXTENSION=agents/ten_packages/extension/<target_extension>
```

## Notes

- `property.json` for the main example is gitignored in this repository, so tracked diffs may not show it.
- Do not edit generated files such as `.ten/`, `BUILD.gn`, `manifest-lock.json`, or server binaries by hand.
