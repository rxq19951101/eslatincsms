#!/bin/bash
#
# 在服务器上安装 docker-compose（使用国内镜像）
# 在服务器上直接执行: bash install_docker_compose.sh
#

echo "=== 安装 docker-compose ==="

# 删除旧文件
rm -f /usr/local/bin/docker-compose

# 方法1: 使用 wget 从 GitHub 下载（如果网络允许）
echo "方法1: 从 GitHub 下载..."
wget -O /usr/local/bin/docker-compose https://github.com/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64 2>&1

# 检查文件大小（应该约12MB）
FILE_SIZE=$(stat -c%s /usr/local/bin/docker-compose 2>/dev/null || echo 0)
echo "文件大小: $FILE_SIZE 字节"

if [ $FILE_SIZE -lt 1000000 ]; then
    echo "文件太小，可能是错误页面，尝试方法2..."
    rm -f /usr/local/bin/docker-compose
    
    # 方法2: 使用 curl 从 GitHub 下载
    echo "方法2: 使用 curl 下载..."
    curl -L https://github.com/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64 -o /usr/local/bin/docker-compose 2>&1
    
    FILE_SIZE=$(stat -c%s /usr/local/bin/docker-compose 2>/dev/null || echo 0)
    if [ $FILE_SIZE -lt 1000000 ]; then
        echo "下载失败，文件大小: $FILE_SIZE"
        echo "请手动下载或使用代理"
        exit 1
    fi
fi

# 设置权限
chmod +x /usr/local/bin/docker-compose

# 验证安装
echo ""
echo "=== 验证安装 ==="
docker-compose --version

if [ $? -eq 0 ]; then
    echo "✓ docker-compose 安装成功"
else
    echo "✗ docker-compose 安装失败"
    exit 1
fi

