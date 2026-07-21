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

# app_super 是集群级角色，不属于 Alembic schema。仅在本地/测试启动链中幂等配置；
# 生产环境由 DBA 显式管理，此脚本不会自动变更生产角色。
case "${ENVIRONMENT:-development}" in
    development|test|local)
        echo ""
        echo "确保 app_super 角色和本地权限..."
        psql "${DATABASE_URL:?DATABASE_URL must be set}" \
            --set=ON_ERROR_STOP=1 \
            --file=/app/scripts/ensure_app_super_role.sql
        echo "✓ app_super 角色已配置"
        ;;
    *)
        echo "跳过 app_super 自动配置（非本地/测试环境）"
        ;;
esac

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

    # 空数据库 bootstrap 必须显式注入密码；禁止固定或生成默认密码。
    missing_bootstrap_passwords=""
    if [ -z "${CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD:-}" ]; then
        missing_bootstrap_passwords="CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD"
    fi
    if [ -z "${CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD:-}" ]; then
        missing_bootstrap_passwords="${missing_bootstrap_passwords:+$missing_bootstrap_passwords, }CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD"
    fi
    if [ -n "$missing_bootstrap_passwords" ]; then
        echo "❌ 空数据库 bootstrap 缺少必需环境变量: $missing_bootstrap_passwords"
        exit 1
    fi
    
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
