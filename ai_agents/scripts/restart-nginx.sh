#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "🔄 重启 Nginx 服务..."

# 重启 nginx 容器
docker compose restart nginx

echo ""
echo "⏳ 等待 Nginx 启动..."
sleep 3

# 检查 Nginx 配置
echo ""
echo "🔍 测试 Nginx 配置..."
docker compose exec nginx nginx -t

echo ""
echo "✅ Nginx 重启完成！"