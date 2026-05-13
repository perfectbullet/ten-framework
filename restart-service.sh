#!/bin/bash
# 远程重启 Voice Assistant 服务脚本

# ============ 配置区 ============
SERVER_USER="zenking"              # SSH 用户名
SERVER_HOST="192.168.8.234"     # 服务器地址
# =================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Voice Assistant 远程重启服务${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

echo -e "${YELLOW}[1/2] 连接服务器并重启服务...${NC}"
echo ""

ssh "${SERVER_USER}@${SERVER_HOST}" bash << 'ENDSSH'
cd /data/metahuman_work/ten-framework/ai_agents/
docker compose exec -T ten_agent_dev bash << 'ENDDOCKER'
cd /app/agents/examples/voice-assistant
./manage.sh restart --clean
ENDDOCKER
ENDSSH

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}[2/2] ✓ 服务重启成功${NC}"
else
    echo ""
    echo -e "${YELLOW}[2/2] ✗ 服务重启失败${NC}"
    exit 1
fi
