#!/bin/bash
#
# 修复数据库用户脚本
# 用于创建或重置 ocpp_user 用户

set -e

echo "=========================================="
echo "修复数据库用户配置"
echo "=========================================="
echo ""

COMPOSE_FILE="docker-compose.prod.yml"

# 检查 docker-compose 文件
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "错误: $COMPOSE_FILE 不存在"
    exit 1
fi

echo "步骤1: 检查数据库容器状态..."
if ! docker compose -f "$COMPOSE_FILE" ps db | grep -q "Up"; then
    echo "错误: 数据库容器未运行，请先启动数据库"
    echo "执行: docker compose -f $COMPOSE_FILE up -d db"
    exit 1
fi

echo "✓ 数据库容器正在运行"
echo ""

echo "步骤2: 检查现有用户..."
EXISTING_USER=$(docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -t -c "SELECT 1 FROM pg_roles WHERE rolname='ocpp_user';" 2>/dev/null | tr -d ' ' || echo "")

if [ "$EXISTING_USER" = "1" ]; then
    echo "✓ 用户 ocpp_user 已存在"
    echo ""
    echo "步骤3: 重置用户密码..."
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "ALTER USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>/dev/null || {
        echo "⚠️  无法使用 postgres 用户，尝试使用其他方法..."
        # 尝试使用环境变量中的用户
        POSTGRES_USER=$(docker compose -f "$COMPOSE_FILE" config | grep -A 2 "POSTGRES_USER" | grep -v "#" | awk '{print $2}' | head -1 | tr -d '"' || echo "ocpp_user")
        if [ "$POSTGRES_USER" != "postgres" ] && [ -n "$POSTGRES_USER" ]; then
            echo "使用用户 $POSTGRES_USER 创建/重置 ocpp_user..."
            docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d postgres -c "ALTER USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>/dev/null || {
                echo "尝试创建用户..."
                docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d postgres -c "CREATE USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>/dev/null || true
            }
        fi
    }
else
    echo "用户 ocpp_user 不存在，正在创建..."
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "CREATE USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>/dev/null || {
        echo "⚠️  无法使用 postgres 用户，尝试使用环境变量中的用户..."
        POSTGRES_USER=$(docker compose -f "$COMPOSE_FILE" config | grep -A 2 "POSTGRES_USER" | grep -v "#" | awk '{print $2}' | head -1 | tr -d '"' || echo "ocpp_user")
        if [ -n "$POSTGRES_USER" ] && [ "$POSTGRES_USER" != "ocpp_user" ]; then
            docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d postgres -c "CREATE USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>/dev/null || true
        fi
    }
fi

echo ""
echo "步骤4: 授予数据库权限..."
docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE ocpp TO ocpp_user;" 2>/dev/null || {
    POSTGRES_USER=$(docker compose -f "$COMPOSE_FILE" config | grep -A 2 "POSTGRES_USER" | grep -v "#" | awk '{print $2}' | head -1 | tr -d '"' || echo "ocpp_user")
    if [ -n "$POSTGRES_USER" ] && [ "$POSTGRES_USER" != "postgres" ]; then
        docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE ocpp TO ocpp_user;" 2>/dev/null || true
    fi
}

echo ""
echo "步骤5: 测试数据库连接..."
if docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✓ 数据库连接测试成功"
else
    echo "⚠️  数据库连接测试失败，但用户可能已创建"
    echo "   请检查密码是否正确，或手动验证连接"
fi

echo ""
echo "=========================================="
echo "修复完成"
echo "=========================================="
echo ""
echo "下一步："
echo "  1. 重启 CSMS 服务以应用新的数据库配置："
echo "     docker compose -f $COMPOSE_FILE restart csms"
echo ""
echo "  2. 或使用 manage.sh："
echo "     ./manage.sh restart"
echo ""
