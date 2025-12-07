# 生产环境配置指南

本文档说明如何配置和部署 OCPP CSMS 系统到生产环境。

## 📋 前置要求

### 系统要求
- **操作系统**: Linux (Ubuntu 16.04+ / CentOS 7+)
- **Docker**: 20.10.7+
- **Docker Compose**: 1.29.2+ (支持 version 2)
- **内存**: 至少 2GB (推荐 4GB+)
- **磁盘**: 至少 10GB 可用空间

### 端口要求
- `9000`: CSMS API 服务
- `3000`: Admin 管理平台
- `1883`: MQTT Broker (可选)
- `5432`: PostgreSQL (建议仅内网)
- `6379`: Redis (建议仅内网)

## 🚀 快速开始

### 1. 准备配置文件

复制并编辑生产环境配置文件：

```bash
# 复制环境变量模板
cp .env.production .env.production.local

# 编辑配置文件（必须修改以下项）
nano .env.production.local
```

**必须修改的配置项：**
- `DB_PASSWORD`: 数据库密码（强密码）
- `SECRET_KEY`: 应用密钥（至少32字符的随机字符串）
- `NEXT_PUBLIC_CSMS_HTTP`: 生产服务器地址（如 `http://your-domain.com:9000`）
- `CORS_ORIGINS`: 允许的前端域名列表

### 2. 运行初始化脚本

```bash
# 创建必要目录、设置权限、生成密钥等
./scripts/init_production.sh
```

### 3. 检查环境

```bash
# 检查系统环境、配置、端口等
./scripts/check_production.sh
```

### 4. 部署服务

```bash
# 构建并启动所有服务
./scripts/deploy_production.sh
```

## 📁 配置文件说明

### `.env.production`

生产环境环境变量配置文件，包含：

- **数据库配置**: PostgreSQL 连接信息
- **Redis 配置**: 缓存服务配置
- **MQTT 配置**: MQTT Broker 配置
- **安全配置**: 密钥、CORS、TLS 等
- **服务端口**: 各服务端口配置
- **传输协议**: MQTT/WebSocket/HTTP 启用配置

### `docker-compose.prod.yml`

生产环境 Docker Compose 配置，使用 `version: "2"` 格式以兼容旧版 docker-compose。

包含以下服务：
- `db`: PostgreSQL 15 数据库
- `redis`: Redis 7 缓存
- `mqtt-broker`: Mosquitto MQTT Broker
- `csms`: CSMS 后端服务
- `admin`: Admin 管理平台

## 🔧 手动部署步骤

如果不想使用自动化脚本，可以手动执行：

### 1. 创建目录

```bash
mkdir -p logs backups
chmod 755 logs backups
```

### 2. 配置环境变量

```bash
# 复制配置文件
cp .env.production .env

# 编辑配置
nano .env
```

### 3. 构建镜像

```bash
docker-compose -f docker-compose.prod.yml build
```

### 4. 启动服务

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### 5. 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.prod.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.prod.yml logs -f csms
```

## 🔍 服务管理

### 查看服务状态

```bash
docker-compose -f docker-compose.prod.yml ps
```

### 停止服务

```bash
docker-compose -f docker-compose.prod.yml down
```

### 重启服务

```bash
docker-compose -f docker-compose.prod.yml restart
```

### 更新服务

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose -f docker-compose.prod.yml up -d --build
```

## 📊 健康检查

### 检查服务健康

```bash
# CSMS 健康检查
curl http://localhost:9000/health

# Admin 健康检查
curl http://localhost:3000
```

### 运行完整检查

```bash
./scripts/check_production.sh
```

## 💾 数据备份

### 手动备份

```bash
# 使用备份脚本
./scripts/backup.sh

# 或手动备份
docker exec ocpp-db-prod pg_dump -U ocpp_user ocpp_prod > backups/backup_$(date +%Y%m%d_%H%M%S).sql
```

### 自动备份（Cron）

```bash
# 编辑 crontab
crontab -e

# 添加每日备份（每天凌晨2点）
0 2 * * * cd /path/to/eslatincsms && ./scripts/backup.sh
```

## 🔒 安全配置

### 1. 修改默认密码

确保 `.env.production` 中所有密码都已修改：
- `DB_PASSWORD`
- `SECRET_KEY`
- `REDIS_PASSWORD` (可选)
- `MQTT_PASSWORD` (可选)

### 2. 配置防火墙

```bash
# 开放必要端口
sudo ufw allow 9000/tcp  # CSMS API
sudo ufw allow 3000/tcp  # Admin
sudo ufw allow 1883/tcp  # MQTT (如果需要外网访问)

# 限制数据库和 Redis 仅内网访问（推荐）
# 不要将 5432 和 6379 暴露到公网
```

### 3. 启用 HTTPS (推荐)

使用 Nginx 反向代理并配置 SSL 证书：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. 限制 CORS

在 `.env.production` 中配置：

```bash
CORS_ORIGINS=["https://your-domain.com","https://admin.your-domain.com"]
```

## 📝 日志管理

### 查看日志

```bash
# 所有服务
docker-compose -f docker-compose.prod.yml logs -f

# 特定服务
docker-compose -f docker-compose.prod.yml logs -f csms
docker-compose -f docker-compose.prod.yml logs -f admin

# 最近100行
docker-compose -f docker-compose.prod.yml logs --tail=100 csms
```

### 日志文件位置

- 应用日志: `./logs/` 目录
- Docker 日志: `docker logs <container_name>`

## 🐛 故障排查

### 服务无法启动

1. 检查日志：
```bash
docker-compose -f docker-compose.prod.yml logs
```

2. 检查端口占用：
```bash
netstat -tuln | grep -E '9000|3000|5432|6379|1883'
```

3. 检查环境变量：
```bash
cat .env
```

### 数据库连接失败

1. 检查数据库服务：
```bash
docker exec ocpp-db-prod pg_isready -U ocpp_user
```

2. 检查数据库密码是否正确

3. 检查网络连接：
```bash
docker network inspect eslatincsms_ocppnet
```

### 服务健康检查失败

1. 等待服务完全启动（可能需要30-60秒）

2. 检查服务状态：
```bash
docker-compose -f docker-compose.prod.yml ps
```

3. 手动测试：
```bash
curl http://localhost:9000/health
```

## 📚 相关文档

- [环境版本清单](./ENVIRONMENT_VERSIONS.md)
- [部署检查清单](./docs/deployment/PRODUCTION_CHECKLIST.md)
- [生产部署指南](./docs/deployment/PRODUCTION_DEPLOYMENT.md)

## 🆘 获取帮助

如遇问题，请：
1. 查看日志文件
2. 运行 `./scripts/check_production.sh` 检查环境
3. 查看 [故障排查文档](./docs/troubleshooting/)

