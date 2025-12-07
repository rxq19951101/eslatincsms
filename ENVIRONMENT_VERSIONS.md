# 项目环境版本清单

本文档列出项目中使用的所有软件版本，方便配置服务器环境。

## 🐳 Docker 相关

### Docker Compose
- **版本要求**: `1.29.2` 或更高（支持 version 2 格式）
- **注意**: 服务器上的 docker-compose 需要支持 version 2 格式
- **下载地址**: 
  - GitHub: https://github.com/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64
  - 国内镜像: https://get.daocloud.io/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64

### Docker Compose 文件版本
- **开发环境**: `version: "3.9"` (docker-compose.yml)
- **生产环境**: `version: "3.9"` (docker-compose.prod.yml)
- **服务器兼容**: 需要改为 `version: "2"` (旧版本docker-compose不支持3.9)

## 🐍 Python 环境

### Python 版本
- **CSMS 服务**: `Python 3.11-slim`
- **充电桩模拟器**: `Python 3.11-slim`
- **基础镜像**: `python:3.11-slim`

### Python 主要依赖 (csms/requirements.txt)
```
fastapi==0.115.2
uvicorn[standard]==0.30.6
websockets==12.0
redis==5.0.8
pydantic==2.9.2
pydantic-settings==2.5.2
python-multipart==0.0.9
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
alembic==1.13.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.1
python-json-logger==2.0.7
prometheus-client==0.20.0
httpx==0.27.2
paho-mqtt==2.1.0
```

### Python 依赖 (charger-sim/requirements.txt)
```
websockets==12.0
qrcode[pil]==7.4.2
requests==2.31.0
paho-mqtt==2.1.0
```

## 🟢 Node.js 环境

### Node.js 版本
- **Admin 管理平台**: `Node.js 20-alpine`
- **基础镜像**: `node:20-alpine`
- **App 移动应用**: 使用 Expo，需要 Node.js 18+ (本地开发)

### Admin 平台依赖 (admin/package.json)
```json
{
  "next": "14.2.5",
  "react": "18.3.1",
  "react-dom": "18.3.1",
  "swr": "^2.2.5",
  "recharts": "^3.5.1",
  "leaflet": "^1.9.4",
  "react-leaflet": "^4.2.1",
  "qrcode.react": "^3.1.0"
}
```

### App 移动应用依赖 (app/package.json)
```json
{
  "expo": "^54.0.21",
  "react": "19.1.0",
  "react-native": "0.81.5",
  "typescript": "~5.9.2",
  "@react-navigation/native": "^6.1.18",
  "@react-navigation/stack": "^6.4.1",
  "@react-navigation/bottom-tabs": "^6.5.20",
  "expo-constants": "^18.0.11",
  "expo-camera": "^17.0.8",
  "expo-location": "~19.0.7"
}
```

## 🗄️ 数据库

### PostgreSQL
- **版本**: `postgres:15-alpine`
- **端口**: `5432`
- **默认数据库**: `ocpp` (开发) / `ocpp_prod` (生产)
- **驱动**: `psycopg2-binary==2.9.9`

### Redis
- **版本**: `redis:7-alpine`
- **端口**: `6379`
- **Python 客户端**: `redis==5.0.8`
- **持久化**: 生产环境启用 AOF

## 📡 MQTT Broker

### Mosquitto
- **镜像**: `eclipse-mosquitto:latest`
- **端口**: `1883` (默认)
- **Python 客户端**: `paho-mqtt==2.1.0`

## 🌐 Web 框架

### FastAPI (CSMS 后端)
- **版本**: `0.115.2`
- **ASGI 服务器**: `uvicorn[standard]==0.30.6`
- **端口**: `9000`

### Next.js (Admin 前端)
- **版本**: `14.2.5`
- **React**: `18.3.1`
- **端口**: `3000` (开发) / `3000` (生产)

## 📱 移动应用

### Expo
- **版本**: `^54.0.21`
- **React Native**: `0.81.5`
- **React**: `19.1.0`
- **TypeScript**: `~5.9.2`

## 🔧 服务器环境要求

### 最低要求
- **操作系统**: Linux (Ubuntu 16.04+ / CentOS 7+)
- **Docker**: `20.10.7+`
- **Docker Compose**: `1.29.2+` (支持 version 2)
- **内存**: 至少 2GB (推荐 4GB+)
- **磁盘**: 至少 10GB 可用空间

### 端口占用
- `9000`: CSMS 后端服务
- `3000`: Admin 管理平台
- `5432`: PostgreSQL (可选，建议仅内网)
- `6379`: Redis (可选，建议仅内网)
- `1883`: MQTT Broker (可选)

## 📦 容器镜像清单

### 基础镜像
- `python:3.11-slim` - Python 应用
- `node:20-alpine` - Node.js 应用
- `postgres:15-alpine` - 数据库
- `redis:7-alpine` - 缓存
- `eclipse-mosquitto:latest` - MQTT Broker

### 构建镜像
- `eslatincsms-csms:latest` - CSMS 后端 (需要构建)
- `eslatincsms-admin:latest` - Admin 前端 (需要构建)
- `eslatincsms-charger-sim:latest` - 充电桩模拟器 (需要构建)

## 🔄 版本兼容性说明

### Docker Compose 版本兼容
- **version 3.9**: 需要 docker-compose 1.25.0+
- **version 2**: 兼容旧版本 docker-compose (1.6.0+)
- **服务器建议**: 使用 version 2 以确保兼容性

### Python 版本兼容
- **Python 3.11**: 所有 Python 依赖均支持
- **最低要求**: Python 3.9+ (部分依赖可能需要)

### Node.js 版本兼容
- **Node.js 20**: Next.js 14 和 Expo 54 均支持
- **最低要求**: Node.js 18+ (Next.js 14 要求)

## 📝 环境变量配置

### 必需环境变量 (.env)
```bash
# 数据库
DB_USER=ocpp_user
DB_PASSWORD=your_secure_password
DB_NAME=ocpp_prod
DATABASE_URL=postgresql://ocpp_user:password@db:5432/ocpp_prod

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=  # 可选

# 服务端口
CSMS_PORT=9000
ADMIN_PORT=3000

# Admin 前端 API 地址
NEXT_PUBLIC_CSMS_HTTP=http://your-server-ip:9000
```

## 🚀 快速检查清单

在服务器上执行以下命令检查环境：

```bash
# 检查 Docker
docker --version          # 应显示 20.10.7+
docker-compose --version  # 应显示 1.29.2+

# 检查端口占用
netstat -tuln | grep -E '9000|3000|5432|6379|1883'

# 检查磁盘空间
df -h

# 检查内存
free -h
```

## 📚 相关文档

- Docker Compose 安装: https://docs.docker.com/compose/install/
- Python 3.11 文档: https://docs.python.org/3.11/
- Node.js 20 文档: https://nodejs.org/docs/latest-v20.x/
- Next.js 14 文档: https://nextjs.org/docs
- Expo 54 文档: https://docs.expo.dev/

