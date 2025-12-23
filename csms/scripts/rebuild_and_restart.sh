#!/bin/bash
#
# 重构 CSMS 镜像并重启服务
# 使用方法: ./rebuild_and_restart.sh [选项]
#

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认配置
COMPOSE_FILE="docker-compose.prod.yml"
SERVICE_NAME="csms"
CONTAINER_NAME="ocpp-csms-prod"
BUILD_ARGS=""
NO_CACHE=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --service)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --help)
            echo "使用方法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --no-cache        不使用缓存构建（完全重新构建）"
            echo "  --compose-file    指定 docker-compose 文件（默认: docker-compose.prod.yml）"
            echo "  --service         指定服务名（默认: csms）"
            echo "  --help            显示此帮助信息"
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "重构 CSMS 镜像并重启服务"
echo "=========================================="
echo "Compose 文件: $COMPOSE_FILE"
echo "服务名: $SERVICE_NAME"
echo "容器名: $CONTAINER_NAME"
echo "=========================================="
echo ""

# 检查 docker-compose 文件是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}错误: 找不到 docker-compose 文件: $COMPOSE_FILE${NC}"
    exit 1
fi

# 1. 停止服务
echo -e "${YELLOW}步骤 1: 停止服务...${NC}"
docker-compose -f "$COMPOSE_FILE" stop "$SERVICE_NAME" || true
echo -e "${GREEN}✓ 服务已停止${NC}"
echo ""

# 2. 重新构建镜像
echo -e "${YELLOW}步骤 2: 重新构建镜像...${NC}"
echo "这可能需要几分钟时间..."
docker-compose -f "$COMPOSE_FILE" build $NO_CACHE "$SERVICE_NAME"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 镜像构建成功${NC}"
else
    echo -e "${RED}✗ 镜像构建失败${NC}"
    exit 1
fi
echo ""

# 3. 启动服务
echo -e "${YELLOW}步骤 3: 启动服务...${NC}"
docker-compose -f "$COMPOSE_FILE" up -d "$SERVICE_NAME"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 服务已启动${NC}"
else
    echo -e "${RED}✗ 服务启动失败${NC}"
    exit 1
fi
echo ""

# 4. 等待服务就绪
echo -e "${YELLOW}步骤 4: 等待服务就绪...${NC}"
sleep 3

# 5. 检查服务状态
echo -e "${YELLOW}步骤 5: 检查服务状态...${NC}"
if docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}✓ 容器正在运行${NC}"
    
    # 检查健康状态
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "no-healthcheck")
    if [ "$HEALTH" != "no-healthcheck" ]; then
        echo "健康状态: $HEALTH"
    fi
else
    echo -e "${RED}✗ 容器未运行${NC}"
    echo "查看日志:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=50 "$SERVICE_NAME"
    exit 1
fi
echo ""

# 6. 检查服务响应
echo -e "${YELLOW}步骤 6: 检查服务响应...${NC}"
sleep 2
if curl -s -f "http://localhost:9000/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 服务健康检查通过${NC}"
else
    echo -e "${YELLOW}⚠ 健康检查未通过，但容器正在运行${NC}"
    echo "可能需要更多时间启动，请稍后检查"
fi
echo ""

# 7. 显示日志（最后几行）
echo -e "${YELLOW}步骤 7: 查看启动日志（最后20行）...${NC}"
docker-compose -f "$COMPOSE_FILE" logs --tail=20 "$SERVICE_NAME"
echo ""

echo "=========================================="
echo -e "${GREEN}重构和启动完成！${NC}"
echo "=========================================="
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose -f $COMPOSE_FILE logs -f $SERVICE_NAME"
echo "  查看状态: docker ps | grep $CONTAINER_NAME"
echo "  重启服务: docker-compose -f $COMPOSE_FILE restart $SERVICE_NAME"
echo "  停止服务: docker-compose -f $COMPOSE_FILE stop $SERVICE_NAME"
echo ""

