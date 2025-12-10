#!/bin/bash
#
# 重新构建并替换 csms Docker 镜像的脚本
#

echo "=========================================="
echo "重新构建 csms Docker 镜像"
echo "=========================================="

# 1. 停止 csms 容器（如果正在运行）
echo "1. 停止 csms 容器..."
docker compose stop csms

# 2. 删除 csms 容器（可选，强制删除）
echo "2. 删除 csms 容器..."
docker compose rm -f csms

# 3. 删除旧的 csms 镜像（可选，强制重建）
echo "3. 删除旧的 csms 镜像..."
docker rmi eslatincsms-csms 2>/dev/null || echo "   (镜像不存在或已被其他容器使用，跳过)"

# 4. 重新构建 csms 镜像（不使用缓存，确保完全重建）
echo "4. 重新构建 csms 镜像..."
docker compose build --no-cache csms

# 5. 启动 csms 服务
echo "5. 启动 csms 服务..."
docker compose up -d csms

# 6. 查看日志（可选）
echo "6. 查看 csms 日志..."
echo "   使用 'docker compose logs -f csms' 查看实时日志"
echo ""

# 7. 检查服务状态
echo "7. 检查服务状态..."
docker compose ps csms

echo ""
echo "=========================================="
echo "完成！csms 服务已重新构建并启动"
echo "=========================================="
