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
    if python3 -c "
import psycopg2
import os
import sys
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://ocpp_user:ocpp_password@db:5432/ocpp'))
    conn.close()
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
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

# 检查数据库是否已初始化
echo ""
echo "检查数据库是否已初始化..."
TABLES_COUNT=$(python3 -c "
import psycopg2
import os
conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://ocpp_user:ocpp_password@db:5432/ocpp'))
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'\")
count = cur.fetchone()[0]
print(count)
conn.close()
")

if [ "$TABLES_COUNT" -gt "5" ]; then
    echo "✓ 数据库已包含 $TABLES_COUNT 个表，跳过表结构初始化"
else
    echo "数据库表数量: $TABLES_COUNT，开始初始化表结构..."
    
    # 执行初始化SQL
    if [ -f "/app/scripts/init_database.sql" ]; then
        echo "执行 init_database.sql..."
        # 从 DATABASE_URL 中提取数据库信息
        DB_HOST=$(echo $DATABASE_URL | sed -n 's|.*@\([^:]*\):[0-9]*/.*|\1|p')
        DB_USER=$(echo $DATABASE_URL | sed -n 's|.*://\([^:]*\):.*|\1|p')
        DB_PASS=$(echo $DATABASE_URL | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
        DB_NAME=$(echo $DATABASE_URL | sed -n 's|.*/\([^?]*\).*|\1|p')
        
        export PGPASSWORD="${DB_PASS}"
        psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -f /app/scripts/init_database.sql
        
        if [ $? -eq 0 ]; then
            echo "✓ 数据库表结构初始化成功"
        else
            echo "❌ 数据库表结构初始化失败"
            exit 1
        fi
    else
        echo "⚠️  未找到 init_database.sql 文件"
    fi
fi

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
