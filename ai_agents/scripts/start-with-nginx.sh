#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "🚀 启动 TEN Agent 开发环境（带 Nginx）"
echo ""

# 检查是否存在 SSL 证书
if [ ! -f "nginx/ssl/nginx-selfsigned.crt" ]; then
    echo "⚠️  未找到 SSL 证书，正在生成..."
    bash scripts/generate-ssl-cert.sh
    echo ""
fi

# 创建必要的目录
echo "📁 创建必要的目录..."
mkdir -p nginx/logs
mkdir -p nginx/cache
mkdir -p nginx/conf.d

# 复制配置文件（如果不存在）
if [ ! -f "nginx/nginx.conf" ]; then
    echo "⚠️  nginx/nginx.conf 不存在，请先创建配置文件"
    exit 1
fi

if [ ! -f "nginx/conf.d/default.conf" ]; then
    echo "⚠️  nginx/conf.d/default.conf 不存在，请先创建配置文件"
    exit 1
fi

echo ""
echo "🐳 启动 Docker 容器..."
docker compose up -d

echo ""
echo "⏳ 等待服务启动..."
sleep 5

echo ""
echo "✅ 服务启动完成！"
echo ""
echo "📋 访问地址："
echo "  • Frontend (HTTPS):        https://localhost:3000"
echo "  • Agent Server (HTTP):     http://localhost:8080"
echo "  • RTC Port 1 (HTTP):       http://localhost:9000"
echo "  • RTC Port 2 (HTTP):       http://localhost:9001"
echo "  • Graph Designer (HTTP):   http://localhost:49483"
echo ""
echo "📊 日志文件位置："
echo "  • Nginx 日志:    nginx/logs/"
echo "  • 应用日志:      ${LOG_PATH:-logs/}"
echo ""
echo "🔍 查看日志命令："
echo "  • docker compose logs -f nginx"
echo "  • docker compose logs -f ten_agent_dev"
echo ""
echo "⚠️  注意：首次访问 HTTPS 时，浏览器会提示证书不受信任（自签名证书），点击「继续访问」即可"