#!/bin/bash
#
# 删除数据库卷的脚本
# 用于清理数据库数据
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认使用生产环境配置
COMPOSE_FILE="${1:-docker-compose.prod.yml}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}删除数据库卷${NC}"
echo -e "${GREEN}使用配置文件: $COMPOSE_FILE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 确认操作
echo -e "${RED}警告：此操作将永久删除所有数据库数据！${NC}"
echo ""
echo "将删除以下卷："
echo "  - postgres_data (PostgreSQL 数据库数据)"
echo "  - redis_data (Redis 数据)"
echo "  - mqtt_data (MQTT 数据)"
echo "  - mqtt_logs (MQTT 日志)"
echo ""
read -p "确认删除？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

# 停止并删除容器和卷
echo ""
echo -e "${BLUE}停止所有容器并删除卷...${NC}"
docker compose -f "$COMPOSE_FILE" down -v || true

# 手动删除卷（如果还存在）
echo ""
echo -e "${BLUE}删除所有相关卷...${NC}"

# 获取项目名称
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

# 删除命名卷
for volume in postgres_data redis_data mqtt_data mqtt_logs; do
    full_volume_name="${PROJECT_NAME}_${volume}"
    if docker volume ls | grep -q "$full_volume_name"; then
        echo "删除卷: $full_volume_name"
        docker volume rm "$full_volume_name" || true
    fi
    # 也尝试不带项目前缀的名称
    if docker volume ls | grep -q "^local.*${volume}$"; then
        echo "删除卷: $volume"
        docker volume rm "$volume" || true
    fi
done

# 清理所有未使用的卷
echo ""
echo -e "${BLUE}清理所有未使用的卷...${NC}"
docker volume prune -f || true

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}完成！所有数据库卷已删除${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}注意：下次启动服务时，数据库将重新初始化${NC}"
echo ""
