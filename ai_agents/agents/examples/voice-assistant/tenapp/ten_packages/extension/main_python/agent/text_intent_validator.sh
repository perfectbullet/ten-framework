#!/bin/bash
set -e

cd "$(dirname "$0")"

# export OPENAI_API_KEY=sk-ldtkmrwzqnhmzrgeednfbdulupqjjcaimcwdcwyofxmwljqi
# export OPENAI_MODEL=Qwen/Qwen2.5-72B-Instruct
# export OPENAI_BASE_URL=https://api.siliconflow.cn/v12

# export OPENAI_BASE_URL=http://192.168.100.230:11434/v1
# export OPENAI_MODEL=qwen2.5:14b

# export OPENAI_BASE_URL=http://192.168.8.233:8200/v1
export OPENAI_BASE_URL=http://192.168.100.230:8200/v1
export OPENAI_MODEL=Qwen3-14B-AWQ

echo "=== Environment ==="
echo "  OPENAI_BASE_URL = $OPENAI_BASE_URL"
echo "  OPENAI_MODEL    = $OPENAI_MODEL"
echo "  OPENAI_API_KEY  = ${OPENAI_API_KEY:0:8}..."
echo "==================="

python text_intent_validator.py
