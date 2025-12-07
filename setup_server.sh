#!/bin/bash
#
# 服务器部署脚本
# 在服务器上执行此脚本完成所有配置
#

set -e

echo "=========================================="
echo "OCPP 充电桩管理系统 - 服务器部署脚本"
echo "=========================================="
echo ""

# 检查是否在项目目录
if [ ! -f "docker-compose.prod.yml" ]; then
    echo "错误: 请在项目根目录执行此脚本"
    exit 1
fi

# 1. 检查 Docker 环境
echo "=== 1. 检查 Docker 环境 ==="
if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装"
    exit 1
fi
docker --version

if ! command -v docker-compose &> /dev/null; then
    echo "错误: docker-compose 未安装"
    exit 1
fi
docker-compose --version
echo "✓ Docker 环境检查通过"
echo ""

# 2. 修复 docker-compose 配置
echo "=== 2. 修复 docker-compose 配置 ==="
if [ -f "fix_docker_compose.sh" ]; then
    bash fix_docker_compose.sh
else
    echo "警告: fix_docker_compose.sh 不存在，跳过"
fi
echo ""

# 3. 创建必要的目录
echo "=== 3. 创建必要的目录 ==="
mkdir -p logs backups
chmod 755 logs backups
echo "✓ 目录创建完成"
echo ""

# 4. 检查环境配置文件
echo "=== 4. 检查环境配置文件 ==="
if [ ! -f ".env" ]; then
    if [ -f ".env.production" ]; then
        cp .env.production .env
        echo "✓ 已从 .env.production 创建 .env"
    else
        echo "警告: .env 文件不存在，请创建并配置："
        echo "  DB_USER=ocpp_user"
        echo "  DB_PASSWORD=your_password"
        echo "  DB_NAME=ocpp_prod"
        echo "  DATABASE_URL=postgresql://ocpp_user:your_password@db:5432/ocpp_prod"
        echo "  REDIS_URL=redis://redis:6379/0"
        echo "  CSMS_PORT=9000"
        echo "  ADMIN_PORT=3000"
        echo "  NEXT_PUBLIC_CSMS_HTTP=http://your-server-ip:9000"
        echo ""
        read -p "是否现在创建 .env 文件? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cat > .env << 'ENVEOF'
# 数据库配置
DB_USER=ocpp_user
DB_PASSWORD=请修改为安全密码
DB_NAME=ocpp_prod
DATABASE_URL=postgresql://ocpp_user:请修改为安全密码@db:5432/ocpp_prod

# Redis配置
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=

# 服务端口
CSMS_PORT=9000
ADMIN_PORT=3000

# Admin前端API地址（使用服务器公网IP）
NEXT_PUBLIC_CSMS_HTTP=http://47.98.214.8:9000
ENVEOF
            echo "✓ 已创建 .env 文件，请编辑并修改密码"
            echo "  使用命令: nano .env"
            exit 0
        fi
    fi
else
    echo "✓ .env 文件已存在"
fi
echo ""

# 5. 构建并启动服务
echo "=== 5. 构建并启动服务 ==="
read -p "是否现在构建并启动服务? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "开始构建镜像..."
    docker-compose -f docker-compose.prod.yml build
    
    echo ""
    echo "启动服务..."
    docker-compose -f docker-compose.prod.yml up -d
    
    echo ""
    echo "=== 服务状态 ==="
    docker-compose -f docker-compose.prod.yml ps
    
    echo ""
    echo "=== 查看日志 ==="
    echo "使用以下命令查看日志:"
    echo "  docker-compose -f docker-compose.prod.yml logs -f"
    echo ""
    echo "=== 检查服务健康 ==="
    sleep 5
    curl -s http://localhost:9000/health && echo " - CSMS 服务正常" || echo " - CSMS 服务未就绪"
    curl -s http://localhost:3000 > /dev/null && echo " - Admin 服务正常" || echo " - Admin 服务未就绪"
else
    echo "跳过构建和启动"
    echo ""
    echo "手动执行命令:"
    echo "  docker-compose -f docker-compose.prod.yml up -d --build"
fi

echo ""
echo "=========================================="
echo "部署脚本执行完成！"
echo "=========================================="

