#!/bin/bash
#
# 本地数据库初始化脚本（在 Docker 外执行）
# 使用: ./init_database_local.sh
#

set -e

echo "========================================="
echo "本地数据库初始化脚本"
echo "========================================="

# 检查数据库容器是否运行
if ! docker ps | grep -q ocpp-db-prod; then
    echo "❌ 数据库容器未运行"
    echo "请先启动服务: docker compose -f docker-compose.prod.yml up -d"
    exit 1
fi

# 等待数据库就绪
echo "等待数据库就绪..."
for i in {1..30}; do
    if docker exec ocpp-db-prod pg_isready -U ocpp_user > /dev/null 2>&1; then
        echo "✓ 数据库已就绪"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ 数据库连接超时"
        exit 1
    fi
    echo "等待中... ($i/30)"
    sleep 2
done

# 检查是否已初始化
TABLE_COUNT=$(docker exec ocpp-db-prod psql -U ocpp_user -d ocpp -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'" 2>/dev/null || echo "0")
TABLE_COUNT=$(echo $TABLE_COUNT | tr -d ' ')

if [ "$TABLE_COUNT" -gt "5" ]; then
    echo "✓ 数据库已包含 $TABLE_COUNT 个表"
    echo "跳过表结构初始化"
else
    echo "数据库表数量: $TABLE_COUNT，开始初始化表结构..."
    docker exec -i ocpp-db-prod psql -U ocpp_user -d ocpp < csms/scripts/init_database.sql
    
    if [ $? -eq 0 ]; then
        echo "✓ 数据库表结构初始化成功"
    else
        echo "❌ 数据库表结构初始化失败"
        exit 1
    fi
fi

# 检查是否需要创建初始数据
ADMIN_COUNT=$(docker exec ocpp-db-prod psql -U ocpp_user -d ocpp -t -c "SELECT COUNT(*) FROM admin_users" 2>/dev/null || echo "0")
ADMIN_COUNT=$(echo $ADMIN_COUNT | tr -d ' ')

if [ "$ADMIN_COUNT" -gt "0" ]; then
    echo "✓ 已存在 $ADMIN_COUNT 个管理员用户"
    echo "跳过初始数据创建"
else
    echo "管理员用户数量: $ADMIN_COUNT，开始创建初始数据..."
    docker exec ocpp-csms-prod python3 /app/scripts/create_initial_data.py
    
    if [ $? -eq 0 ]; then
        echo "✓ 初始数据创建成功"
    else
        echo "❌ 初始数据创建失败"
        exit 1
    fi
fi

echo ""
echo "========================================="
echo "✓ 数据库初始化完成"
echo "========================================="
echo ""
echo "默认管理员账号信息："
echo "  用户名: admin"
echo "  密码: admin123"
echo "  邮箱: admin@example.com"
echo ""
echo "测试登录:"
echo "  访问: http://localhost:3000/login"
echo ""
