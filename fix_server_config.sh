#!/bin/bash
#
# 修复服务器配置脚本
# 用于设置正确的API地址环境变量
#

echo "=========================================="
echo "服务器配置修复脚本"
echo "=========================================="
echo ""

# 获取服务器IP（如果未提供）
if [ -z "$1" ]; then
    echo "请输入服务器IP地址（例如：47.236.134.99）:"
    read SERVER_IP
else
    SERVER_IP=$1
fi

if [ -z "$SERVER_IP" ]; then
    echo "错误：服务器IP地址不能为空"
    exit 1
fi

echo "使用服务器IP: $SERVER_IP"
echo ""

# 设置环境变量
export NEXT_PUBLIC_CSMS_HTTP="http://${SERVER_IP}:9000"

echo "已设置环境变量:"
echo "  NEXT_PUBLIC_CSMS_HTTP=$NEXT_PUBLIC_CSMS_HTTP"
echo ""

# 创建或更新 .env.prod 文件
ENV_FILE=".env.prod"
if [ -f "$ENV_FILE" ]; then
    # 如果文件存在，更新或添加配置
    if grep -q "NEXT_PUBLIC_CSMS_HTTP" "$ENV_FILE"; then
        # 更新现有配置
        sed -i.bak "s|NEXT_PUBLIC_CSMS_HTTP=.*|NEXT_PUBLIC_CSMS_HTTP=http://${SERVER_IP}:9000|" "$ENV_FILE"
        echo "已更新 $ENV_FILE 文件"
    else
        # 添加新配置
        echo "NEXT_PUBLIC_CSMS_HTTP=http://${SERVER_IP}:9000" >> "$ENV_FILE"
        echo "已添加配置到 $ENV_FILE 文件"
    fi
else
    # 创建新文件
    cat > "$ENV_FILE" << EOL
# 生产环境配置
NEXT_PUBLIC_CSMS_HTTP=http://${SERVER_IP}:9000
CSMS_PORT=9000
ADMIN_PORT=3000
MQTT_BROKER_PORT=1883
EOL
    echo "已创建 $ENV_FILE 文件"
fi

echo ""
echo "=========================================="
echo "配置完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 重启Docker服务："
echo "   docker compose -f docker-compose.prod.yml down"
echo "   docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "2. 或者使用环境变量启动："
echo "   NEXT_PUBLIC_CSMS_HTTP=http://${SERVER_IP}:9000 docker compose -f docker-compose.prod.yml up -d"
echo ""
