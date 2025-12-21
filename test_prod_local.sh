#!/bin/bash
#
# 本地测试生产环境配置脚本
# 使用与生产环境完全相同的配置进行本地测试

set -e

COMPOSE_FILE="docker-compose.local-prod.yml"

echo "=========================================="
echo "本地测试生产环境配置"
echo "=========================================="
echo ""
echo "使用配置文件: $COMPOSE_FILE"
echo "配置与生产环境完全一致，便于测试"
echo ""

# 检查 docker-compose 文件
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "错误: $COMPOSE_FILE 不存在"
    exit 1
fi

echo "步骤1: 停止现有服务（如果运行中）..."
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

echo ""
echo "步骤2: 构建并启动服务..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo ""
echo "步骤3: 等待服务启动..."
sleep 10

echo ""
echo "步骤4: 检查服务状态..."
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "步骤5: 检查数据库连接..."
sleep 5
if docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -c "SELECT current_database();" > /dev/null 2>&1; then
    echo "✓ 数据库连接正常"
else
    echo "⚠️  数据库连接失败"
fi

echo ""
echo "步骤6: 检查 CSMS 健康状态..."
sleep 5
if curl -sf http://localhost:9000/health > /dev/null 2>&1; then
    echo "✓ CSMS 服务健康"
    curl -s http://localhost:9000/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:9000/health
else
    echo "⚠️  CSMS 服务不健康或未启动"
    echo "查看日志: docker compose -f $COMPOSE_FILE logs csms --tail=20"
fi

echo ""
echo "=========================================="
echo "测试环境已启动"
echo "=========================================="
echo ""
echo "服务地址:"
echo "  - CSMS API: http://localhost:9000"
echo "  - API文档: http://localhost:9000/docs"
echo "  - Admin: http://localhost:3000"
echo "  - MQTT: localhost:1883"
echo ""
echo "查看日志:"
echo "  docker compose -f $COMPOSE_FILE logs -f"
echo ""
echo "停止服务:"
echo "  docker compose -f $COMPOSE_FILE down"
echo ""
echo "停止并删除数据卷:"
echo "  docker compose -f $COMPOSE_FILE down -v"
echo ""
