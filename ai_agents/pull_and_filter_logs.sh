#!/bin/bash
set -e

# REMOTE="zenking@192.168.8.233:/data/metahuman_work/ten-framework/ai_agents/agents/examples/voice-assistant/info-interupt.log"
REMOTE="zenking@10.1.0.100:/data/metahuman_work/ten-framework/ai_agents/agents/examples/voice-assistant/info.log"


echo "=== 1. 拉取日志 ==="
rsync -avz --progress "$REMOTE" ./

echo ""
echo "=== 2. 清理日志：去除 [employee_xxx] 开头的行 ==="
grep -v '^\[employee_' info.log > info-clean.log
echo "info-clean 已生成 ($(wc -l < info.log) 行)"


echo ""
echo "=== 完成 ==="
ls -lh info-clean.log
