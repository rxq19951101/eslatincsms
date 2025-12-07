#!/bin/bash
#
# 生产环境初始化脚本
# 初始化数据库、创建目录、设置权限等
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}OCPP CSMS 生产环境初始化${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查环境变量文件
ENV_FILE="$PROJECT_DIR/.env.production"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}错误: 未找到 .env.production 文件${NC}"
    echo -e "${YELLOW}请先创建并配置 .env.production 文件${NC}"
    exit 1
fi

source "$ENV_FILE" 2>/dev/null || true

# 1. 创建必要的目录
echo -e "${YELLOW}[1] 创建必要的目录...${NC}"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
mkdir -p "$PROJECT_DIR/data/postgres"
mkdir -p "$PROJECT_DIR/data/redis"
mkdir -p "$PROJECT_DIR/data/mqtt"

# 设置目录权限
chmod 755 "$PROJECT_DIR/logs"
chmod 755 "$PROJECT_DIR/backups"
chmod 755 "$PROJECT_DIR/data"

echo -e "${GREEN}✓ 目录创建完成${NC}"
echo ""

# 2. 复制环境变量文件
echo -e "${YELLOW}[2] 配置环境变量...${NC}"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$ENV_FILE" "$PROJECT_DIR/.env"
    echo -e "${GREEN}✓ 已复制 .env.production 到 .env${NC}"
else
    echo -e "${YELLOW}⚠ .env 文件已存在，跳过${NC}"
fi
echo ""

# 3. 生成随机密钥（如果未设置）
echo -e "${YELLOW}[3] 检查安全配置...${NC}"
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY_AT_LEAST_32_CHARACTERS" ]; then
    NEW_SECRET_KEY=$(openssl rand -hex 32)
    echo -e "${YELLOW}生成新的 SECRET_KEY...${NC}"
    
    # 更新 .env 文件
    if grep -q "^SECRET_KEY=" "$PROJECT_DIR/.env"; then
        sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET_KEY/" "$PROJECT_DIR/.env"
    else
        echo "SECRET_KEY=$NEW_SECRET_KEY" >> "$PROJECT_DIR/.env"
    fi
    
    # 更新 .env.production 文件
    if grep -q "^SECRET_KEY=" "$ENV_FILE"; then
        sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET_KEY/" "$ENV_FILE"
    else
        echo "SECRET_KEY=$NEW_SECRET_KEY" >> "$ENV_FILE"
    fi
    
    echo -e "${GREEN}✓ SECRET_KEY 已生成并更新${NC}"
else
    echo -e "${GREEN}✓ SECRET_KEY 已配置${NC}"
fi
echo ""

# 4. 检查数据库密码
echo -e "${YELLOW}[4] 检查数据库配置...${NC}"
if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "CHANGE_THIS_SECURE_PASSWORD" ]; then
    echo -e "${RED}错误: 请在 .env.production 中设置 DB_PASSWORD${NC}"
    exit 1
else
    echo -e "${GREEN}✓ 数据库密码已配置${NC}"
fi
echo ""

# 5. 初始化数据库（如果服务已运行）
echo -e "${YELLOW}[5] 检查数据库服务...${NC}"
cd "$PROJECT_DIR"

if docker ps --format '{{.Names}}' | grep -q "^ocpp-db-prod$"; then
    echo -e "${YELLOW}数据库服务已运行，等待就绪...${NC}"
    sleep 5
    
    # 检查数据库连接
    if docker exec ocpp-db-prod pg_isready -U "${DB_USER:-ocpp_user}" -d "${DB_NAME:-ocpp_prod}" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 数据库连接正常${NC}"
        
        # 运行数据库初始化（如果存在）
        if [ -f "$PROJECT_DIR/csms/scripts/init_db.py" ]; then
            echo -e "${YELLOW}运行数据库初始化脚本...${NC}"
            docker exec ocpp-csms-prod python -m csms.scripts.init_db 2>/dev/null || \
            docker exec ocpp-csms-prod python scripts/init_db.py 2>/dev/null || \
            echo -e "${YELLOW}⚠ 数据库初始化脚本未找到或执行失败${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ 数据库尚未就绪${NC}"
    fi
else
    echo -e "${YELLOW}⚠ 数据库服务未运行，将在部署时初始化${NC}"
fi
echo ""

# 6. 设置防火墙规则（可选）
echo -e "${YELLOW}[6] 防火墙配置提示...${NC}"
echo -e "${BLUE}如需开放端口，请执行以下命令：${NC}"
echo -e "${BLUE}  - CSMS API (9000):${NC} sudo ufw allow 9000/tcp"
echo -e "${BLUE}  - Admin (3000):${NC} sudo ufw allow 3000/tcp"
echo -e "${BLUE}  - MQTT (1883):${NC} sudo ufw allow 1883/tcp"
echo ""

# 7. 创建备份脚本
echo -e "${YELLOW}[7] 创建备份脚本...${NC}"
cat > "$PROJECT_DIR/scripts/backup.sh" << 'EOF'
#!/bin/bash
# 数据库备份脚本

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ocpp_backup_$TIMESTAMP.sql"

mkdir -p "$BACKUP_DIR"

docker exec ocpp-db-prod pg_dump -U ocpp_user ocpp_prod > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "备份成功: $BACKUP_FILE"
    # 保留最近 7 天的备份
    find "$BACKUP_DIR" -name "ocpp_backup_*.sql" -mtime +7 -delete
else
    echo "备份失败"
    exit 1
fi
EOF

chmod +x "$PROJECT_DIR/scripts/backup.sh"
echo -e "${GREEN}✓ 备份脚本已创建${NC}"
echo ""

# 完成
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}初始化完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步："
echo "  1. 检查并修改 .env.production 中的配置"
echo "  2. 运行部署脚本: ./scripts/deploy_production.sh"
echo "  3. 运行检查脚本: ./scripts/check_production.sh"
echo ""

