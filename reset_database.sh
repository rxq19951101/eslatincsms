#!/bin/bash
#
# 重置数据库（删除旧数据并重新初始化）
# 警告：这会删除所有数据库数据！
#

set -e

echo "=========================================="
echo "重置数据库"
echo "=========================================="
echo ""
echo "⚠️  警告：这将删除所有数据库数据！"
echo ""
read -p "确认继续？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "1. 停止相关服务..."
docker compose -f docker-compose.prod.yml stop db csms 2>&1 || true

echo ""
echo "2. 删除数据库卷..."
docker compose -f docker-compose.prod.yml down -v db 2>&1 || true
docker volume rm eslatincsms_postgres_data 2>&1 || true

echo ""
echo "3. 重新启动数据库..."
docker compose -f docker-compose.prod.yml up -d db

echo ""
echo "4. 等待数据库就绪..."
sleep 5

# 等待数据库健康检查通过
for i in {1..30}; do
    if docker compose -f docker-compose.prod.yml ps db | grep -q "healthy"; then
        echo "✓ 数据库已就绪"
        break
    fi
    echo "等待数据库启动... ($i/30)"
    sleep 2
done

echo ""
echo "5. 验证数据库用户..."
if docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT current_user, current_database();" > /dev/null 2>&1; then
    echo "✓ 数据库用户验证成功"
    docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT current_user, current_database();" 2>&1
else
    echo "✗ 数据库用户验证失败"
    echo "尝试使用环境变量检查..."
    docker compose -f docker-compose.prod.yml exec db env | grep POSTGRES
    exit 1
fi

echo ""
echo "6. 重启CSMS服务..."
docker compose -f docker-compose.prod.yml restart csms

echo ""
echo "=========================================="
echo "数据库重置完成"
echo "=========================================="
echo ""
echo "数据库已重新初始化，用户: ocpp_user, 密码: ocpp_password"
echo ""

