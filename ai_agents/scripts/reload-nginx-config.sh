#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "🔄 重新加载 Nginx 配置..."

# 测试配置文件语法
echo "🔍 测试配置文件语法..."
docker compose exec nginx nginx -t

if [ $? -eq 0 ]; then
    # 重新加载配置（不中断服务）
    echo "✅ 配置文件语法正确，重新加载..."
    docker compose exec nginx nginx -s reload
    echo "✅ Nginx 配置重新加载完成！"
else
    echo "❌ 配置文件语法错误，请检查配置文件"
    exit 1
fi