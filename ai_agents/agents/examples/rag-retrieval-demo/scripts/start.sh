#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"

echo "========================================="
echo "Starting RAG Retrieval Demo"
echo "========================================="

cd "$PROJECT_ROOT/tenapp"

# 激活 Python 虚拟环境
export PYTHONPATH="$PROJECT_ROOT/tenapp/ten_packages/extension/rag_retrieval_python/.venv/lib/python3.10/site-packages:$PYTHONPATH"

# 启动应用
echo "Starting TEN application..."
go run main.go > "$LOG_DIR/app.log" 2>&1 &

APP_PID=$!
echo $APP_PID > "$LOG_DIR/app.pid"

echo "========================================="
echo "Application started successfully!"
echo "PID: $APP_PID"
echo "Logs: $LOG_DIR/app.log"
echo "========================================="