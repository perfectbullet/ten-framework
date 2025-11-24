#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "🛑 停止 TEN Agent 开发环境"
docker compose down

echo "✅ 服务已停止"