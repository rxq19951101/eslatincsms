#!/bin/bash
#
# 修复数据库不存在的问题
# 创建数据库和用户

set -e

echo "=========================================="
echo "修复数据库不存在问题"
echo "=========================================="
echo ""

COMPOSE_FILE="docker-compose.prod.yml"

echo "步骤1: 检查数据库容器状态..."
if ! docker compose -f "$COMPOSE_FILE" ps db | grep -q "Up"; then
    echo "错误: 数据库容器未运行"
    exit 1
fi

echo "✓ 数据库容器正在运行"
echo ""

echo "步骤2: 检查数据库是否存在..."
DB_EXISTS=$(docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname='ocpp';" 2>/dev/null | tr -d ' ' || echo "")

if [ "$DB_EXISTS" = "1" ]; then
    echo "✓ 数据库 'ocpp' 已存在"
else
    echo "数据库 'ocpp' 不存在，正在创建..."
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d postgres -c "CREATE DATABASE ocpp;" 2>&1
    if [ $? -eq 0 ]; then
        echo "✓ 数据库已创建"
    else
        echo "⚠️  使用 ocpp_user 创建失败，尝试使用 postgres 用户..."
        # 如果 ocpp_user 没有创建数据库的权限，尝试使用 postgres
        docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "CREATE DATABASE ocpp OWNER ocpp_user;" 2>&1 || {
            echo "尝试其他方法..."
            # 检查实际用户
            ACTUAL_USER=$(docker compose -f "$COMPOSE_FILE" exec -T db env | grep "^POSTGRES_USER=" | cut -d'=' -f2 || echo "ocpp_user")
            if [ "$ACTUAL_USER" != "ocpp_user" ] && [ -n "$ACTUAL_USER" ]; then
                echo "使用用户 $ACTUAL_USER 创建数据库..."
                docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$ACTUAL_USER" -d postgres -c "CREATE DATABASE ocpp OWNER ocpp_user;" 2>&1 || true
            fi
        }
    fi
fi

echo ""
echo "步骤3: 授予 ocpp_user 数据库权限..."
docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE ocpp TO ocpp_user;" 2>&1 || {
    # 如果失败，尝试使用 postgres 用户
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE ocpp TO ocpp_user;" 2>&1 || true
}

echo ""
echo "步骤4: 测试数据库连接..."
TEST=$(docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -c "SELECT current_database(), current_user;" 2>&1)
if echo "$TEST" | grep -q "ocpp"; then
    echo "✓ 数据库连接测试成功"
    echo "  数据库: ocpp"
    echo "  用户: ocpp_user"
else
    echo "⚠️  连接测试失败"
    echo "$TEST" | tail -5
fi

echo ""
echo "=========================================="
echo "修复完成"
echo "=========================================="
echo ""
echo "下一步："
echo "  重启 CSMS 服务："
echo "    docker compose -f $COMPOSE_FILE restart csms"
echo ""
