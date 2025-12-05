#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "Installing RAG Retrieval Demo"
echo "========================================="

cd "$PROJECT_ROOT/tenapp"

# 安装 Python 依赖
echo "Installing Python dependencies..."
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv first."
    exit 1
fi

cd ten_packages/extension/rag_retrieval_python
uv venv .venv
source .venv/bin/activate
uv pip install -e .
deactivate

cd "$PROJECT_ROOT/tenapp"

# 安装 Go 依赖
echo "Installing Go dependencies..."
go mod tidy

echo "========================================="
echo "Installation completed successfully!"
echo "========================================="