#!/bin/bash
# 检查 CSMS 服务连接脚本

echo "=========================================="
echo "CSMS 服务连接检查"
echo "=========================================="

# 获取当前 IP
CURRENT_IP=$(ifconfig | grep -E "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
echo "当前 IP 地址: $CURRENT_IP"
echo ""

# 检查服务状态
echo "1. 检查 Docker 服务状态..."
docker compose ps | grep -E "csms|admin"
echo ""

# 检查端口
echo "2. 检查端口 9000 是否监听..."
netstat -an | grep 9000 | grep LISTEN || lsof -i :9000 | grep LISTEN
echo ""

# 测试本地连接
echo "3. 测试本地连接 (localhost:9000)..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:9000/health 2>&1 | tail -2
echo ""

# 测试 IP 连接
echo "4. 测试 IP 连接 ($CURRENT_IP:9000)..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://$CURRENT_IP:9000/health 2>&1 | tail -2
echo ""

# 测试充电桩端点
echo "5. 测试充电桩端点 ($CURRENT_IP:9000/chargers)..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://$CURRENT_IP:9000/chargers 2>&1 | tail -2
echo ""

echo "=========================================="
echo "如果连接失败，请检查："
echo "1. Docker 服务是否运行: docker compose ps"
echo "2. 防火墙是否阻止端口 9000"
echo "3. 手机和电脑是否在同一 WiFi 网络"
echo "4. app/config.ts 中的 IP 地址是否正确"
echo "=========================================="

