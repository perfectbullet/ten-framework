#!/bin/bash
set -e

REMOTE="zenking@192.168.8.233:/data/metahuman_work/ten-framework/ai_agents/agents/examples/voice-assistant/info-interupt.log"

echo "=== 1. 拉取日志 ==="
rsync -avz --progress "$REMOTE" ./

echo ""
echo "=== 2. 清理日志：去除 [employee_xxx] 开头的行 ==="
grep -v '^\[employee_' info-kasile.log > info2.log
echo "info2.log 已生成 ($(wc -l < info2.log) 行)"

echo ""
echo "=== 3. 过滤 [tts] ==="
grep '\[tts\]' info2.log > tts.log
echo "tts.log 已生成 ($(wc -l < tts.log) 行)"

echo ""
echo "=== 4. 过滤 [stt] ==="
grep '\[stt\]' info2.log > stt.log
echo "stt.log 已生成 ($(wc -l < stt.log) 行)"

echo ""
echo "=== 5. 过滤 [main_control] ==="
grep '\[main_control\]' info2.log > main_control.log
echo "main_control.log 已生成 ($(wc -l < main_control.log) 行)"

echo ""
echo "=== 完成 ==="
ls -lh info2.log tts.log stt.log main_control.log
