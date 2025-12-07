#!/bin/bash
#
# 修复缺失的 Dockerfile 脚本
# 如果服务器上缺少 Dockerfile.prod，此脚本会创建它
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}修复缺失的 Dockerfile${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

cd "$PROJECT_DIR"

# 检查并创建 admin/Dockerfile.prod
if [ ! -f "admin/Dockerfile.prod" ]; then
    echo -e "${YELLOW}创建 admin/Dockerfile.prod...${NC}"
    
    cat > admin/Dockerfile.prod << 'EOF'
#
# 生产环境 Dockerfile：用于构建 admin (Next.js 14) 生产镜像
# 使用多阶段构建，先构建应用，再运行生产服务器
#

# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 复制依赖文件
COPY package*.json ./
COPY tsconfig.json next.config.js next-env.d.ts ./

# 安装依赖
RUN npm ci --no-audit --no-fund

# 复制源代码
COPY app ./app

# 构建应用
RUN npm run build

# 生产运行阶段
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# 创建非root用户
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 从构建阶段复制必要文件
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/tsconfig.json ./
COPY --from=builder /app/next-env.d.ts ./
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/app ./app

# 只安装生产依赖
RUN npm ci --only=production --no-audit --no-fund

USER nextjs

EXPOSE 3000

CMD ["npm", "run", "start"]
EOF
    
    echo -e "${GREEN}✓ admin/Dockerfile.prod 已创建${NC}"
else
    echo -e "${GREEN}✓ admin/Dockerfile.prod 已存在${NC}"
fi

# 检查并创建 csms/Dockerfile
if [ ! -f "csms/Dockerfile" ]; then
    echo -e "${YELLOW}创建 csms/Dockerfile...${NC}"
    
    cat > csms/Dockerfile << 'EOF'
#
# 本文件用于构建 csms 服务镜像：基于 Python 3.11-slim 运行 FastAPI 应用。
# 暴露端口 9000，并通过 uvicorn 启动。
#

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=9000
EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
EOF
    
    echo -e "${GREEN}✓ csms/Dockerfile 已创建${NC}"
else
    echo -e "${GREEN}✓ csms/Dockerfile 已存在${NC}"
fi

# 验证文件
echo ""
echo -e "${YELLOW}验证文件...${NC}"
if [ -f "admin/Dockerfile.prod" ] && [ -f "csms/Dockerfile" ]; then
    echo -e "${GREEN}✓ 所有 Dockerfile 文件已就绪${NC}"
    echo ""
    echo "文件位置："
    ls -lh admin/Dockerfile.prod csms/Dockerfile
    echo ""
    echo -e "${GREEN}现在可以重新运行部署脚本：${NC}"
    echo "  ./scripts/deploy_production.sh"
else
    echo -e "${RED}✗ 文件创建失败${NC}"
    exit 1
fi

