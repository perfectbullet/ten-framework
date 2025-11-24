#!/bin/bash

cd "$(dirname "$0")/.."

echo "📋 选择要查看的日志："
echo "  1) Access Log (所有访问日志)"
echo "  2) Error Log (所有错误日志)"
echo "  3) Frontend Access Log"
echo "  4) Agent Server Access Log"
echo "  5) Docker Logs (实时)"
echo ""
read -p "请选择 (1-5): " choice

case $choice in
    1)
        tail -f nginx/logs/access.log
        ;;
    2)
        tail -f nginx/logs/error.log
        ;;
    3)
        tail -f nginx/logs/frontend-access.log
        ;;
    4)
        tail -f nginx/logs/agent-server-access.log
        ;;
    5)
        docker compose logs -f nginx
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac