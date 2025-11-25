#!/bin/bash

# 停止 Docker 服务
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/ai_agents/agents/examples/voice-assistant-with-turn-detection/cerebrium"

echo "🛑 Stopping Turn Detection service..."
docker-compose down

echo "✅ Service stopped successfully!"