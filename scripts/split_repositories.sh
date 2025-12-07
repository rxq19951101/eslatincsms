#!/bin/bash
#
# 将项目拆分为四个独立的 Git 仓库
# csms, admin, app, charger-sim
#

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(dirname "$PROJECT_ROOT")"

echo -e "${BLUE}开始拆分项目为四个独立仓库...${NC}\n"

# 1. 创建 csms 仓库
echo -e "${GREEN}[1/4] 创建 csms 仓库...${NC}"
CSMS_DIR="$PARENT_DIR/eslatincsms-csms"
mkdir -p "$CSMS_DIR"
cd "$CSMS_DIR"
git init

# 复制文件
cp -r "$PROJECT_ROOT/csms" .
cp "$PROJECT_ROOT/docker-compose.prod.yml" . 2>/dev/null || true
cp "$PROJECT_ROOT/.gitignore" .
cp "$PROJECT_ROOT/.env.example" . 2>/dev/null || true

# 创建 README
cat > README.md << 'EOF'
# CSMS - OCPP 1.6J 后端服务

OCPP 充电桩管理系统后端服务，支持 WebSocket、HTTP、MQTT 多种传输方式。

## 功能特性

- ✅ OCPP 1.6 协议完整支持
- ✅ REST API 接口
- ✅ 多传输方式支持（WebSocket、HTTP、MQTT）
- ✅ 充电桩管理
- ✅ 订单管理
- ✅ 消息处理
- ✅ PostgreSQL 数据库
- ✅ Redis 缓存

## 快速开始

### 使用 Docker Compose

```bash
# 创建环境变量文件
cp .env.example .env.production
# 编辑 .env.production 填入配置

# 启动服务
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

### 本地开发

```bash
cd csms
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 端口

- CSMS API: `9000`
- PostgreSQL: `5432`
- Redis: `6379`

## 文档

详细文档请查看 `docs/` 目录。

## 许可证

[您的许可证]
EOF

# 创建 .gitignore（如果不存在）
if [ ! -f .gitignore ]; then
    cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*.so
.Python
venv/
env/
.env
*.log
logs/
*.db
*.sqlite
EOF
fi

git add .
git commit -m "Initial commit: CSMS backend service" || true
echo -e "${GREEN}✓ csms 仓库创建完成${NC}\n"

# 2. 创建 admin 仓库
echo -e "${GREEN}[2/4] 创建 admin 仓库...${NC}"
ADMIN_DIR="$PARENT_DIR/eslatincsms-admin"
mkdir -p "$ADMIN_DIR"
cd "$ADMIN_DIR"
git init

# 复制文件
cp -r "$PROJECT_ROOT/admin" .
cp "$PROJECT_ROOT/.gitignore" .

# 创建 README
cat > README.md << 'EOF'
# Admin - 充电桩管理后台

Next.js 14 构建的充电桩运营管理平台。

## 功能特性

- ✅ 充电桩监测中心（实时状态大屏）
- ✅ 地图视图（Leaflet 地图）
- ✅ 充电桩管理（检测、录入、配置）
- ✅ 客服消息（查看和回复用户消息）
- ✅ 实时数据刷新（每 3 秒）

## 快速开始

### 开发模式

```bash
cd admin
npm install
npm run dev
```

访问 http://localhost:3000

### 生产构建

```bash
npm run build
npm start
```

## 环境变量

```bash
NEXT_PUBLIC_CSMS_HTTP=http://localhost:9000
```

## 依赖

- Next.js 14
- React 18
- TypeScript
- Leaflet (地图)
- SWR (数据获取)

## 许可证

[您的许可证]
EOF

# 创建 .gitignore
cat > .gitignore << 'EOF'
.next/
out/
node_modules/
.env*.local
.DS_Store
*.log
EOF

git add .
git commit -m "Initial commit: Admin management platform" || true
echo -e "${GREEN}✓ admin 仓库创建完成${NC}\n"

# 3. 创建 app 仓库
echo -e "${GREEN}[3/4] 创建 app 仓库...${NC}"
APP_DIR="$PARENT_DIR/eslatincsms-app"
mkdir -p "$APP_DIR"
cd "$APP_DIR"
git init

# 复制文件
cp -r "$PROJECT_ROOT/app" .
cp "$PROJECT_ROOT/.gitignore" .

# 创建 README
cat > README.md << 'EOF'
# App - 充电桩用户端应用

Expo React Native 移动应用，用户端充电桩使用应用。

## 功能特性

- ✅ 扫码充电
- ✅ 地图查看充电桩位置
- ✅ 充电历史记录
- ✅ 消息支持
- ✅ 用户账户管理

## 快速开始

### 开发模式

```bash
cd app
npm install
npm start
```

### 构建生产版本

```bash
# Android
npx expo build:android

# iOS
npx expo build:ios
```

## 环境变量

```bash
EXPO_PUBLIC_CSMS_API_BASE=https://api.yourdomain.com
```

## 依赖

- Expo SDK
- React Native
- React Navigation
- Expo Camera
- React Native Maps

## 许可证

[您的许可证]
EOF

# 创建 .gitignore
cat > .gitignore << 'EOF'
.expo/
.expo-shared/
node_modules/
.env*.local
.DS_Store
*.log
*.jks
*.p8
*.p12
*.key
*.mobileprovision
EOF

git add .
git commit -m "Initial commit: Mobile app" || true
echo -e "${GREEN}✓ app 仓库创建完成${NC}\n"

# 4. 创建 charger-sim 仓库
echo -e "${GREEN}[4/4] 创建 charger-sim 仓库...${NC}"
SIM_DIR="$PARENT_DIR/eslatincsms-charger-sim"
mkdir -p "$SIM_DIR"
cd "$SIM_DIR"
git init

# 复制文件
cp -r "$PROJECT_ROOT/charger-sim" .
cp "$PROJECT_ROOT/.gitignore" .

# 创建 README
cat > README.md << 'EOF'
# Charger Simulator - 充电桩模拟器

OCPP 1.6 充电桩模拟器，支持 WebSocket 和 MQTT 协议。

## 功能特性

- ✅ WebSocket 模拟器
- ✅ MQTT 模拟器
- ✅ 交互式控制
- ✅ 完整 OCPP 1.6 协议支持
- ✅ 自动生成二维码

## 快速开始

### 安装依赖

```bash
cd charger-sim
pip install -r requirements.txt
```

### WebSocket 模拟器

```bash
# 基本用法
python ocpp_simulator.py --id CP-001

# 交互式控制
python interactive.py --id CP-001

# 设置位置
python interactive.py --id CP-001 --lat 39.9 --lng 116.4 --address "北京市"
```

### MQTT 模拟器

```bash
# 确保 MQTT broker 运行
docker run -it -p 1883:1883 eclipse-mosquitto

# 运行模拟器
python mqtt_simulator.py --id CP-MQTT-001
```

## 依赖

- Python 3.10+
- websockets
- paho-mqtt
- qrcode

## 许可证

[您的许可证]
EOF

# 创建 .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*.so
.Python
venv/
env/
*.log
.DS_Store
EOF

git add .
git commit -m "Initial commit: Charger simulator" || true
echo -e "${GREEN}✓ charger-sim 仓库创建完成${NC}\n"

# 总结
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}拆分完成！四个独立仓库已创建：${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "1. ${YELLOW}eslatincsms-csms${NC}      - 后端服务"
echo -e "2. ${YELLOW}eslatincsms-admin${NC}     - 管理后台"
echo -e "3. ${YELLOW}eslatincsms-app${NC}       - 移动应用"
echo -e "4. ${YELLOW}eslatincsms-charger-sim${NC} - 充电桩模拟器"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}下一步：${NC}"
echo -e "1. 在每个仓库目录中检查文件"
echo -e "2. 在 GitHub 上创建对应的仓库"
echo -e "3. 连接远程仓库并推送代码"
echo -e "\n示例："
echo -e "  cd eslatincsms-csms"
echo -e "  git remote add origin https://github.com/YOUR_USERNAME/eslatincsms-csms.git"
echo -e "  git push -u origin main"

