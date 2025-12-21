#!/bin/bash
#
# 应用新配置脚本
# 重置数据库密码并重启服务

set -e

COMPOSE_FILE="docker-compose.prod.yml"

echo "=========================================="
echo "应用新配置"
echo "=========================================="
echo ""

echo "步骤1: 重置数据库密码为 'ocpp_password'..."
docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d postgres -c "ALTER USER ocpp_user WITH PASSWORD 'ocpp_password';" 2>&1
if [ $? -eq 0 ]; then
    echo "✓ 数据库密码已重置"
else
    echo "⚠️  密码重置失败，但继续执行"
fi

echo ""
echo "步骤2: 停止所有服务..."
docker compose -f "$COMPOSE_FILE" down

echo ""
echo "步骤3: 重新启动服务（应用新配置）..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "步骤4: 等待服务启动..."
sleep 10

echo ""
echo "步骤5: 检查服务状态..."
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "步骤6: 检查数据库连接错误..."
ERRORS=$(docker compose -f "$COMPOSE_FILE" logs csms --tail=30 2>&1 | grep -i "authentication failed" || echo "")
if [ -z "$ERRORS" ]; then
    echo "✓ 未发现认证错误"
else
    echo "⚠️  仍然有认证错误："
    echo "$ERRORS" | tail -5
fi

echo ""
echo "=========================================="
echo "配置应用完成"
echo "=========================================="
echo ""
echo "查看日志："
echo "  docker compose -f $COMPOSE_FILE logs csms --tail=20"
echo ""
