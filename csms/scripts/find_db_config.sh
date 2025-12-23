#!/bin/bash
#
# 查找数据库容器配置的脚本
#

echo "=========================================="
echo "查找数据库配置"
echo "=========================================="
echo ""

# 查找数据库容器
echo "1. 查找数据库容器:"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep -E "(postgres|db|NAME)"
echo ""

# 检查环境变量
CONTAINER_NAME="${1:-ocpp-db-prod}"
echo "2. 检查容器 '$CONTAINER_NAME' 的环境变量:"
if docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "POSTGRES 相关环境变量:"
    docker exec "$CONTAINER_NAME" env | grep POSTGRES
    echo ""
    
    echo "3. 列出所有数据库:"
    docker exec "$CONTAINER_NAME" psql -U postgres -l 2>/dev/null || \
    docker exec "$CONTAINER_NAME" psql -U ocpp_user -l 2>/dev/null || \
    docker exec "$CONTAINER_NAME" psql -U local -l 2>/dev/null
    echo ""
    
    echo "4. 尝试连接测试:"
    echo "   使用 postgres 用户:"
    docker exec "$CONTAINER_NAME" psql -U postgres -c "SELECT current_database();" 2>&1 | head -5
    echo ""
else
    echo "容器 '$CONTAINER_NAME' 不存在或未运行"
    echo ""
    echo "可用的容器:"
    docker ps --format "{{.Names}}"
fi

