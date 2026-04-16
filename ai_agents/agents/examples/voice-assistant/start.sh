#!/bin/bash

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo "====================================="
echo "Voice Assistant 启动脚本"
echo "====================================="

# 清理临时文件
echo "[1/4] 清理临时文件..."
CLEANED=0

# 清理 send_audio_save 目录下的音频文件 (pcm, wav)
if [ -d "./tenapp/send_audio_save" ]; then
    COUNT=$(find ./tenapp/send_audio_save -type f \( -name "*.pcm" -o -name "*.wav" \) 2>/dev/null | wc -l)
    if [ "$COUNT" -gt 0 ]; then
        find ./tenapp/send_audio_save -type f \( -name "*.pcm" -o -name "*.wav" \) -delete 2>/dev/null
        echo "  ✓ 清理 send_audio_save: $COUNT 个音频文件"
        CLEANED=$((CLEANED + COUNT))
    fi
fi

# 清理 vad_dump 目录下的 wav 文件
if [ -d "./tenapp/vad_dump" ]; then
    COUNT=$(find ./tenapp/vad_dump -type f -name "*.wav" 2>/dev/null | wc -l)
    if [ "$COUNT" -gt 0 ]; then
        find ./tenapp/vad_dump -type f -name "*.wav" -delete 2>/dev/null
        echo "  ✓ 清理 vad_dump: $COUNT 个 wav 文件"
        CLEANED=$((CLEANED + COUNT))
    fi
fi

# 清理 msg_dict_json 目录下的 json 文件
if [ -d "./tenapp/msg_dict_json" ]; then
    COUNT=$(find ./tenapp/msg_dict_json -type f -name "*.json" 2>/dev/null | wc -l)
    if [ "$COUNT" -gt 0 ]; then
        find ./tenapp/msg_dict_json -type f -name "*.json" -delete 2>/dev/null
        echo "  ✓ 清理 msg_dict_json: $COUNT 个 json 文件"
        CLEANED=$((CLEANED + COUNT))
    fi
fi

if [ "$CLEANED" -eq 0 ]; then
    echo "  - 无临时文件需要清理"
fi

# 清理之前的程序
echo "[2/4] 清理之前的进程..."
pkill -f "task run" 2>/dev/null
pkill -f "./bin/api" 2>/dev/null
sleep 1

# 设置环境变量
echo "[3/4] 设置环境变量..."
export AGORA_APP_ID=c51a83813c654291981c09ff195b38a0
export AGORA_APP_CERTIFICATE=1ab5fa2b3c834169a18b5f07d44d1359
export OPENAI_API_BASE=http://192.168.8.233:11434/v1
export OPENAI_MODEL=qwen2.5:14b
export EMPLOYEE_API_BASE_URL=http://192.168.8.233:8100

# 后台启动
echo "[4/4] 启动服务..."
nohup task run > info.log 2>&1 &
PID=$!

sleep 1

echo ""
echo "✓ 服务已启动 (PID: $PID)"
echo "  日志文件:  info.log"
echo "  查看日志:  tail -f info.log"
echo "  停止服务:  pkill -f 'task run'"

echo ""
echo "====================================="
echo "进程环境变量:"
echo "====================================="
# 打印进程的环境变量
cat /proc/$PID/environ 2>/dev/null | tr '\0' '\n' | grep -E "^(OPENAI_|AGORA_|EMPLOYEE)" | sort
echo "====================================="

echo ""
