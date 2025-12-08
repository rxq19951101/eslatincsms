#!/bin/bash
#
# 本地测试生产环境 Docker Compose
# 用于在本地模拟生产环境进行测试
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}本地生产环境测试脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未找到 Docker，请先安装 Docker${NC}"
    exit 1
fi

# 检查 Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: 未找到 docker-compose，请先安装 docker-compose${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker 环境检查通过${NC}"

# 检查环境变量文件
ENV_FILE="$PROJECT_DIR/.env.production"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}错误: 未找到 .env.production 文件${NC}"
    exit 1
fi

# 创建本地测试用的 .env 文件
echo -e "${YELLOW}准备环境变量...${NC}"
cp "$ENV_FILE" "$PROJECT_DIR/.env"

# 检查必要的环境变量并设置默认值
source "$ENV_FILE" 2>/dev/null || true

# 设置默认值（如果未设置）
export DB_PASSWORD=${DB_PASSWORD:-"local_test_password_123"}
export SECRET_KEY=${SECRET_KEY:-"local_test_secret_key_at_least_32_characters_long"}
export DATABASE_URL=${DATABASE_URL:-"postgresql://${DB_USER:-ocpp_user}:${DB_PASSWORD}@db:5432/${DB_NAME:-ocpp_prod}"}
export REDIS_PASSWORD=${REDIS_PASSWORD:-""}
export MQTT_BROKER_HOST=${MQTT_BROKER_HOST:-"mqtt-broker"}
export MQTT_BROKER_PORT=${MQTT_BROKER_PORT:-"1883"}
export MQTT_USERNAME=${MQTT_USERNAME:-""}
export MQTT_PASSWORD=${MQTT_PASSWORD:-""}
export MQTT_TOPIC_PREFIX=${MQTT_TOPIC_PREFIX:-"ocpp"}
export ENABLE_MQTT_TRANSPORT=${ENABLE_MQTT_TRANSPORT:-"true"}
export ENABLE_WEBSOCKET_TRANSPORT=${ENABLE_WEBSOCKET_TRANSPORT:-"false"}
export ENABLE_HTTP_TRANSPORT=${ENABLE_HTTP_TRANSPORT:-"false"}
export CSMS_PORT=${CSMS_PORT:-"9000"}
export ADMIN_PORT=${ADMIN_PORT:-"3000"}
export NEXT_PUBLIC_CSMS_HTTP=${NEXT_PUBLIC_CSMS_HTTP:-"http://localhost:9000"}

# 更新 .env 文件
cat > "$PROJECT_DIR/.env" <<EOF
# 本地测试环境变量（从 .env.production 生成）
APP_NAME=${APP_NAME:-OCPP 1.6J CSMS}
APP_VERSION=${APP_VERSION:-1.0.0}
ENVIRONMENT=production
DEBUG=false

HOST=0.0.0.0
PORT=9000
CSMS_PORT=${CSMS_PORT}
ADMIN_PORT=${ADMIN_PORT}

DB_USER=${DB_USER:-ocpp_user}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME:-ocpp_prod}
DB_HOST=db
DATABASE_URL=${DATABASE_URL}

REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
REDIS_PASSWORD=${REDIS_PASSWORD}

MQTT_BROKER_HOST=${MQTT_BROKER_HOST}
MQTT_BROKER_PORT=${MQTT_BROKER_PORT}
MQTT_USERNAME=${MQTT_USERNAME}
MQTT_PASSWORD=${MQTT_PASSWORD}
MQTT_TOPIC_PREFIX=${MQTT_TOPIC_PREFIX}

ENABLE_MQTT_TRANSPORT=${ENABLE_MQTT_TRANSPORT}
ENABLE_WEBSOCKET_TRANSPORT=${ENABLE_WEBSOCKET_TRANSPORT}
ENABLE_HTTP_TRANSPORT=${ENABLE_HTTP_TRANSPORT}

SECRET_KEY=${SECRET_KEY}
LOG_LEVEL=${LOG_LEVEL:-INFO}
LOG_FORMAT=${LOG_FORMAT:-json}

NEXT_PUBLIC_CSMS_HTTP=${NEXT_PUBLIC_CSMS_HTTP}
NODE_ENV=production
EOF

echo -e "${GREEN}✓ 环境变量已准备${NC}"

# 创建必要的目录
echo -e "${YELLOW}创建必要的目录...${NC}"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
chmod 755 "$PROJECT_DIR/logs" 2>/dev/null || true
chmod 755 "$PROJECT_DIR/backups" 2>/dev/null || true

# 停止现有服务
echo -e "${YELLOW}停止现有服务...${NC}"
cd "$PROJECT_DIR"
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# 检查 Dockerfile 是否存在
if [ ! -f "$PROJECT_DIR/csms/Dockerfile" ]; then
    echo -e "${RED}错误: 未找到 csms/Dockerfile${NC}"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/admin/Dockerfile.prod" ]; then
    echo -e "${RED}错误: 未找到 admin/Dockerfile.prod${NC}"
    exit 1
fi

# 构建镜像
echo -e "${YELLOW}构建 Docker 镜像...${NC}"
echo -e "${YELLOW}这可能需要几分钟时间...${NC}"

# 使用 docker-compose 或 docker compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

$COMPOSE_CMD -f docker-compose.prod.yml build --no-cache

# 启动服务
echo -e "${YELLOW}启动服务...${NC}"
$COMPOSE_CMD -f docker-compose.prod.yml up -d

# 等待服务就绪
echo -e "${YELLOW}等待服务启动（30秒）...${NC}"
sleep 30

# 检查服务状态
echo -e "${YELLOW}检查服务状态...${NC}"
$COMPOSE_CMD -f docker-compose.prod.yml ps

# 检查健康状态
echo -e "${YELLOW}检查服务健康状态...${NC}"
sleep 5

# 检查 CSMS 健康
if curl -f http://localhost:${CSMS_PORT}/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ CSMS 服务健康${NC}"
else
    echo -e "${YELLOW}⚠ CSMS 服务可能尚未就绪，请检查日志${NC}"
    echo -e "${YELLOW}查看日志: $COMPOSE_CMD -f docker-compose.prod.yml logs csms${NC}"
fi

# 检查 Admin 健康
if curl -f http://localhost:${ADMIN_PORT} > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Admin 服务健康${NC}"
else
    echo -e "${YELLOW}⚠ Admin 服务可能尚未就绪，请检查日志${NC}"
    echo -e "${YELLOW}查看日志: $COMPOSE_CMD -f docker-compose.prod.yml logs admin${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}本地测试环境启动完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "服务地址："
echo "  - CSMS API: http://localhost:${CSMS_PORT}"
echo "  - Admin 管理平台: http://localhost:${ADMIN_PORT}"
echo "  - API 文档: http://localhost:${CSMS_PORT}/docs"
echo ""
echo "常用命令："
echo "  查看日志: $COMPOSE_CMD -f docker-compose.prod.yml logs -f"
echo "  查看 CSMS 日志: $COMPOSE_CMD -f docker-compose.prod.yml logs -f csms"
echo "  查看 Admin 日志: $COMPOSE_CMD -f docker-compose.prod.yml logs -f admin"
echo "  停止服务: $COMPOSE_CMD -f docker-compose.prod.yml down"
echo "  重启服务: $COMPOSE_CMD -f docker-compose.prod.yml restart"
echo ""

