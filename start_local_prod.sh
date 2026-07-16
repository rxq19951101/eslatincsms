#!/bin/bash
#
# 本地生产环境完整启动脚本
# 包括：服务启动、数据库初始化、健康检查
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
COMPOSE_FILE="docker-compose.yml"
CSMS_HEALTH_URL="http://localhost:9000/health"
ADMIN_URL="http://localhost:3000"
MAX_WAIT_TIME=120  # 最大等待时间（秒）

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}本地生产环境完整启动${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 Docker
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker 未运行，请先启动 Docker${NC}"
    exit 1
fi

# 检查 docker-compose 文件
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}❌ 配置文件 $COMPOSE_FILE 不存在${NC}"
    exit 1
fi

# 生成默认密钥（如果未设置，用于本地测试）
# 注意：docker-compose.yml 中已有 ENCRYPTION_KEY / SECRET_KEY 默认值（仅本地），这里只是提示
if [ -z "$SECRET_KEY" ]; then
    echo -e "${YELLOW}⚠️  未设置 SECRET_KEY，将使用 docker-compose 中的默认值（仅用于本地测试）${NC}"
fi

if [ -z "$ENCRYPTION_KEY" ]; then
    echo -e "${YELLOW}⚠️  未设置 ENCRYPTION_KEY，将使用 docker-compose 中的默认值（仅用于本地测试）${NC}"
fi
echo ""

# 步骤 1: 停止并清理旧容器（可选）
echo -e "${BLUE}[1/5] 清理旧容器...${NC}"
# 检查是否有运行中的容器
if docker compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo -e "${YELLOW}检测到运行中的容器${NC}"
    docker compose -f "$COMPOSE_FILE" down
    echo -e "${GREEN}✓ 旧容器已清理${NC}"
else
    echo -e "${BLUE}未检测到运行中的容器，跳过清理${NC}"
fi
echo ""

# 步骤 2: 构建镜像
echo -e "${BLUE}[2/5] 构建 Docker 镜像...${NC}"
docker compose -f "$COMPOSE_FILE" build --no-cache
echo -e "${GREEN}✓ 镜像构建完成${NC}"
echo ""

# 步骤 3: 启动基础服务（数据库、Redis、MQTT）
echo -e "${BLUE}[3/5] 启动基础服务（数据库、Redis、MQTT）...${NC}"
docker compose -f "$COMPOSE_FILE" up -d db redis mqtt-broker

# 等待数据库就绪
echo -e "${BLUE}等待数据库就绪...${NC}"
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U ocpp_user -d ocpp > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 数据库已就绪${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ 数据库启动超时${NC}"
        exit 1
    fi
    sleep 2
    echo -n "."
done
echo ""

# 等待 Redis 就绪
echo -e "${BLUE}等待 Redis 就绪...${NC}"
for i in {1..15}; do
    if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis 已就绪${NC}"
        break
    fi
    if [ $i -eq 15 ]; then
        echo -e "${RED}❌ Redis 启动超时${NC}"
        exit 1
    fi
    sleep 2
    echo -n "."
done
echo ""

# 步骤 4: 初始化数据库
echo -e "${BLUE}[4/5] 初始化数据库...${NC}"

# 检查是否需要初始化
DB_INITIALIZED=$(docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tenants';" 2>/dev/null || echo "0")

if [ "$DB_INITIALIZED" = "1" ]; then
    echo -e "${YELLOW}⚠️  数据库表已存在${NC}"
    read -p "是否重新初始化数据库? (这将删除所有数据!) (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}⚠️  正在删除所有表...${NC}"
        docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ocpp_user; GRANT ALL ON SCHEMA public TO public;" || true
    else
        echo -e "${YELLOW}⚠️  跳过数据库初始化${NC}"
        DB_INITIALIZED="skip"
    fi
fi

if [ "$DB_INITIALIZED" != "skip" ]; then
    # 执行 SQL 初始化脚本
    echo -e "${BLUE}执行数据库初始化脚本...${NC}"
    if [ -f "csms/scripts/init_database.sql" ]; then
        docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp -f /dev/stdin < csms/scripts/init_database.sql
        echo -e "${GREEN}✓ SQL 初始化脚本执行完成${NC}"
    else
        echo -e "${YELLOW}⚠️  init_database.sql 不存在，跳过 SQL 初始化${NC}"
    fi
    
    # 运行 Python 初始化脚本（如果存在）
    echo -e "${BLUE}运行 Python 数据库初始化...${NC}"
    if [ -f "csms/scripts/init_db.py" ]; then
        docker compose -f "$COMPOSE_FILE" run --rm csms python scripts/init_db.py || echo -e "${YELLOW}⚠️  Python 初始化脚本执行失败（可能是表已存在）${NC}"
    fi
    
    # 创建初始数据（租户和管理员用户）
    echo -e "${BLUE}创建初始数据（租户和管理员用户）...${NC}"
    # 生成密码哈希
    PASSWORD_HASH=$(docker compose -f "$COMPOSE_FILE" run --rm csms python -c "
from passlib.context import CryptContext
try:
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
except:
    pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
print(pwd_context.hash('admin123'))
" 2>/dev/null | tail -1)
    
    if [ -z "$PASSWORD_HASH" ]; then
        echo -e "${YELLOW}⚠️  无法生成密码哈希，跳过初始数据创建${NC}"
    else
        # 使用 psql 直接执行 SQL（绕过 Python ORM 的 RLS 检查）
        docker compose -f "$COMPOSE_FILE" exec -T db psql -U ocpp_user -d ocpp <<EOF 2>&1 | grep -E "(NOTICE|✓|创建)" || true
DO \$\$
DECLARE
    tenant_count INTEGER;
    admin_count INTEGER;
    tenant_id_val UUID;
    super_admin_id_val UUID;
    tenant_admin_id_val UUID;
    membership_id_val UUID;
BEGIN
    SELECT COUNT(*) INTO tenant_count FROM tenants;
    SELECT COUNT(*) INTO admin_count FROM admin_users;
    
    IF tenant_count > 0 OR admin_count > 0 THEN
        RAISE NOTICE '检测到已有数据，跳过初始化';
        RETURN;
    END IF;
    
    RAISE NOTICE '开始创建初始数据...';
    
    tenant_id_val := gen_random_uuid();
    INSERT INTO tenants (id, name, domain, status, subscription_plan, max_charge_points, max_users, settings, created_at, updated_at)
    VALUES (tenant_id_val, '默认租户', NULL, 'active', 'premium', 100, 1000, '{}'::jsonb, NOW(), NOW());
    
    super_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (super_admin_id_val, 'admin', 'admin@example.com', '$PASSWORD_HASH', '系统管理员', TRUE, TRUE, NOW(), NOW());
    
    tenant_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (tenant_admin_id_val, 'tenant_admin', 'tenant_admin@example.com', '$PASSWORD_HASH', '租户管理员', TRUE, FALSE, NOW(), NOW());
    
    membership_id_val := gen_random_uuid();
    INSERT INTO tenant_memberships (id, tenant_id, admin_user_id, is_primary, status, created_at, updated_at)
    VALUES (membership_id_val, tenant_id_val, tenant_admin_id_val, TRUE, 'active', NOW(), NOW());
    
    RAISE NOTICE '初始数据创建完成！';
END \$\$;
EOF
        echo -e "${GREEN}✓ 初始数据创建完成${NC}"
    fi
fi

echo -e "${GREEN}✓ 数据库初始化完成${NC}"
echo ""

# 步骤 5: 启动 CSMS 和 Admin 服务
echo -e "${BLUE}[5/5] 启动应用服务（CSMS、Admin）...${NC}"
docker compose -f "$COMPOSE_FILE" up -d csms admin

# 等待 CSMS 服务就绪
echo -e "${BLUE}等待 CSMS 服务就绪...${NC}"
elapsed=0
while [ $elapsed -lt $MAX_WAIT_TIME ]; do
    if curl -sf "$CSMS_HEALTH_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ CSMS 服务已就绪${NC}"
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
    echo -n "."
done
echo ""

if [ $elapsed -ge $MAX_WAIT_TIME ]; then
    echo -e "${YELLOW}⚠️  CSMS 服务启动超时，请检查日志${NC}"
    echo "查看日志: docker compose -f $COMPOSE_FILE logs csms"
fi

# 等待 Admin 服务就绪
echo -e "${BLUE}等待 Admin 服务就绪...${NC}"
sleep 10
if curl -sf "$ADMIN_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Admin 服务已就绪${NC}"
else
    echo -e "${YELLOW}⚠️  Admin 服务可能还在启动中，请稍后访问${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ 所有服务启动完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}服务地址:${NC}"
echo "  - CSMS API:        http://localhost:9000"
echo "  - CSMS API 文档:   http://localhost:9000/docs"
echo "  - CSMS 健康检查:   $CSMS_HEALTH_URL"
echo "  - Admin 前端:      $ADMIN_URL"
echo "  - 数据库 (PostgreSQL): localhost:5432"
echo "    - 用户: ocpp_user"
echo "    - 密码: ocpp_password"
echo "    - 数据库: ocpp"
echo "  - Redis:           localhost:6379"
echo "  - MQTT:            localhost:1883"
echo ""
echo -e "${BLUE}常用命令:${NC}"
echo "  查看服务状态:     docker compose -f $COMPOSE_FILE ps"
echo "  查看日志:         docker compose -f $COMPOSE_FILE logs -f"
echo "  查看 CSMS 日志:   docker compose -f $COMPOSE_FILE logs -f csms"
echo "  查看 Admin 日志:  docker compose -f $COMPOSE_FILE logs -f admin"
echo "  停止服务:         docker compose -f $COMPOSE_FILE down"
echo "  重启服务:         docker compose -f $COMPOSE_FILE restart"
echo ""
