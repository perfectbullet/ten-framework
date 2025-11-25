#!/bin/bash

# 启动 Docker 服务
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/ai_agents/agents/examples/voice-assistant-with-turn-detection/cerebrium"

echo "🚀 Starting Turn Detection service..."
docker-compose up -d

echo "⏳ Waiting for service to be healthy..."
sleep 10

docker-compose ps

echo "✅ Service started successfully!"
echo "📝 View logs: docker-compose logs -f"
echo "🩺 Health check: curl http://localhost:50010/health"