#!/bin/bash

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo "====================================="
echo "Voice Assistant 启动脚本"
echo "====================================="

# 清理之前的程序
echo "[1/3] 清理之前的进程..."
pkill -f "task run" 2>/dev/null
pkill -f "./bin/api" 2>/dev/null
sleep 1

# 设置环境变量
echo "[2/3] 设置环境变量..."
export AGORA_APP_ID=e66c97f9d78e42a38e20fe8ac220c4a2
export AGORA_APP_CERTIFICATE=b97a6a60cb8744b7a7081501e163a40d

# 后台启动
echo "[3/3] 启动服务..."
nohup task run > info.log 2>&1 &

sleep 1

echo ""
echo "✓ 服务已启动"
echo "  日志文件:  info.log"
echo "  查看日志:  tail -f info.log"
echo "  停止服务:  pkill -f 'task run'"
echo ""
