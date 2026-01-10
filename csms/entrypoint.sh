#!/bin/bash
#
# CSMS 容器启动入口脚本
# 在启动 uvicorn 之前执行数据库初始化
#

set -e

echo "========================================="
echo "CSMS 容器启动中..."
echo "========================================="

# 1. 执行数据库初始化
if [ -f "/app/scripts/init_db_container.sh" ]; then
    echo "执行数据库初始化..."
    bash /app/scripts/init_db_container.sh
else
    echo "⚠️  未找到数据库初始化脚本，跳过..."
fi

echo ""
echo "========================================="
echo "启动 CSMS 应用服务..."
echo "========================================="

# 2. 启动 uvicorn
exec uvicorn app.main:app --host 0.0.0.0 --port 9000
