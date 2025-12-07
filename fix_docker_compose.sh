#!/bin/bash
#
# 修复 docker-compose.prod.yml 版本兼容性问题
# 在服务器上执行此脚本
#

set -e

echo "=== 修复 Docker Compose 配置文件 ==="

# 进入项目目录
cd ~/eslatincsms || { echo "错误: 项目目录不存在"; exit 1; }

# 备份原文件
if [ -f docker-compose.prod.yml ]; then
    cp docker-compose.prod.yml docker-compose.prod.yml.bak
    echo "✓ 已备份原文件为 docker-compose.prod.yml.bak"
fi

# 创建兼容 version 2 的配置文件
cat > docker-compose.prod.yml << 'EOF'
#
# 生产环境 Docker Compose 配置（兼容 version 2）
# 用于部署运营平台和后端服务到生产服务器
#

version: "2"

services:
  db:
    image: postgres:15-alpine
    container_name: ocpp-db-prod
    environment:
      - POSTGRES_USER=${DB_USER:-ocpp_user}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=${DB_NAME:-ocpp_prod}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - ocppnet
    restart: always

  redis:
    image: redis:7-alpine
    container_name: ocpp-redis-prod
    command: redis-server --appendonly yes ${REDIS_PASSWORD:+--requirepass ${REDIS_PASSWORD}}
    volumes:
      - redis_data:/data
    networks:
      - ocppnet
    restart: always

  csms:
    build:
      context: ./csms
      dockerfile: Dockerfile
    container_name: ocpp-csms-prod
    ports:
      - "${CSMS_PORT:-9000}:9000"
    environment:
      - REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
      - PORT=9000
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      - ./logs:/var/log/csms
    depends_on:
      - db
      - redis
    networks:
      - ocppnet
    restart: always

  admin:
    build:
      context: ./admin
      dockerfile: Dockerfile.prod
    container_name: ocpp-admin-prod
    ports:
      - "${ADMIN_PORT:-3000}:3000"
    environment:
      - NEXT_PUBLIC_CSMS_HTTP=${NEXT_PUBLIC_CSMS_HTTP:-http://localhost:9000}
      - NODE_ENV=production
    depends_on:
      - csms
    networks:
      - ocppnet
    restart: always

volumes:
  postgres_data:
  redis_data:

networks:
  ocppnet:
    driver: bridge
EOF

echo "✓ 已创建兼容 version 2 的配置文件"
echo ""
echo "=== 验证配置 ==="
head -5 docker-compose.prod.yml
echo ""
echo "=== 下一步 ==="
echo "1. 确保 .env 文件存在并配置正确"
echo "2. 运行: docker-compose -f docker-compose.prod.yml up -d --build"

