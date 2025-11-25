#!/bin/bash

# 构建 Docker 镜像
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/ai_agents/agents/examples/voice-assistant-with-turn-detection/cerebrium"

echo "🔨 Building Docker image..."
docker-compose build

echo "✅ Docker image built successfully!"