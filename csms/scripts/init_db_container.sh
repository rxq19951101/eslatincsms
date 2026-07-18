#!/bin/bash
#
# 数据库初始化脚本（在容器启动时自动执行）
# 用于在 Docker 容器中初始化数据库表结构
#

set -e

echo "=================================="
echo "数据库初始化脚本开始执行"
echo "=================================="

# 等待数据库就绪
echo "等待数据库连接就绪..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if pg_isready -h db -p 5432 -U "${POSTGRES_USER:-ocpp_user}" -d "${POSTGRES_DB:-ocpp}" >/dev/null 2>&1; then
        echo "✓ 数据库连接成功"
        break
    fi
    
    retry_count=$((retry_count + 1))
    echo "数据库未就绪，重试 $retry_count/$max_retries..."
    sleep 2
done

if [ $retry_count -eq $max_retries ]; then
    echo "❌ 数据库连接超时"
    exit 1
fi

# Alembic 是唯一 schema 入口；每次启动都升级到 head。
echo ""
echo "执行 Alembic upgrade head..."
cd /app
alembic upgrade head
echo "✓ 数据库 schema 已升级到 Alembic head"

# 检查是否需要创建初始数据
echo ""
echo "检查是否需要创建初始数据..."
ADMIN_COUNT=$(python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://ocpp_user:ocpp_password@db:5432/ocpp'))
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM admin_users')
    count = cur.fetchone()[0]
    print(count)
    conn.close()
except:
    print('0')
")

if [ "$ADMIN_COUNT" -gt "0" ]; then
    echo "✓ 已存在 $ADMIN_COUNT 个管理员用户，跳过初始数据创建"
else
    echo "管理员用户数量: $ADMIN_COUNT，开始创建初始数据..."
    
    # 执行初始数据创建脚本
    if [ -f "/app/scripts/create_initial_data.py" ]; then
        echo "执行 create_initial_data.py..."
        python3 /app/scripts/create_initial_data.py
        
        if [ $? -eq 0 ]; then
            echo "✓ 初始数据创建成功"
        else
            echo "❌ 初始数据创建失败"
            exit 1
        fi
    else
        echo "⚠️  未找到 create_initial_data.py 文件"
    fi
fi

echo ""
echo "=================================="
echo "✓ 数据库初始化完成"
echo "=================================="
echo ""
echo "默认管理员账号信息："
echo "  用户名: admin"
echo "  密码: admin123"
echo "  邮箱: admin@example.com"
echo ""
echo "⚠️  重要提示："
echo "  1. 请立即修改默认密码！"
echo "  2. 建议在生产环境中禁用或删除测试账号"
echo ""
