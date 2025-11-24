#!/bin/bash

# 创建证书目录
mkdir -p nginx/ssl

# 生成自签名证书（有效期 365 天）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/nginx-selfsigned.key \
  -out nginx/ssl/nginx-selfsigned.crt \
  -subj "/C=CN/ST=Beijing/L=Beijing/O=TEN Framework/OU=Development/CN=localhost"

# 生成 dhparam 文件（可选，但推荐用于增强安全性）
openssl dhparam -out nginx/ssl/dhparam.pem 2048

# 设置权限
chmod 600 nginx/ssl/nginx-selfsigned.key
chmod 644 nginx/ssl/nginx-selfsigned.crt
chmod 644 nginx/ssl/dhparam.pem

echo "✅ SSL 证书生成完成！"
echo "证书位置: nginx/ssl/nginx-selfsigned.crt"
echo "私钥位置: nginx/ssl/nginx-selfsigned.key"