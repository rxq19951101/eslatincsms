#!/bin/bash
#
# 检查 API 端点是否可用的诊断脚本
#

API_BASE="${1:-http://47.236.134.99:9000}"

echo "=========================================="
echo "检查 API 端点可用性"
echo "API 基础地址: $API_BASE"
echo "=========================================="
echo ""

# 1. 检查健康检查端点
echo "1. 检查 /health 端点..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/health")
if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo "   ✓ /health 正常 (状态码: $HEALTH_RESPONSE)"
else
    echo "   ✗ /health 异常 (状态码: $HEALTH_RESPONSE)"
fi
echo ""

# 2. 检查旧版 /chargers 端点
echo "2. 检查 /chargers 端点（旧版）..."
CHARGERS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/chargers")
if [ "$CHARGERS_RESPONSE" = "200" ]; then
    echo "   ✓ /chargers 正常 (状态码: $CHARGERS_RESPONSE)"
    echo "   响应内容:"
    curl -s "$API_BASE/chargers" | head -c 200
    echo ""
else
    echo "   ✗ /chargers 异常 (状态码: $CHARGERS_RESPONSE)"
fi
echo ""

# 3. 检查新版 /api/v1/chargers 端点
echo "3. 检查 /api/v1/chargers 端点（新版）..."
V1_CHARGERS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/api/v1/chargers")
if [ "$V1_CHARGERS_RESPONSE" = "200" ]; then
    echo "   ✓ /api/v1/chargers 正常 (状态码: $V1_CHARGERS_RESPONSE)"
    echo "   响应内容:"
    curl -s "$API_BASE/api/v1/chargers" | head -c 200
    echo ""
elif [ "$V1_CHARGERS_RESPONSE" = "404" ]; then
    echo "   ✗ /api/v1/chargers 返回 404 (端点不存在)"
    echo "   可能原因："
    echo "   - API v1 路由未注册"
    echo "   - 数据库连接失败"
    echo "   - 数据库表未初始化"
else
    echo "   ✗ /api/v1/chargers 异常 (状态码: $V1_CHARGERS_RESPONSE)"
    echo "   响应内容:"
    curl -s "$API_BASE/api/v1/chargers" | head -c 500
    echo ""
fi
echo ""

# 4. 检查 API 文档
echo "4. 检查 API 文档..."
DOCS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/docs")
if [ "$DOCS_RESPONSE" = "200" ]; then
    echo "   ✓ API 文档可访问 (状态码: $DOCS_RESPONSE)"
    echo "   访问地址: $API_BASE/docs"
else
    echo "   ✗ API 文档不可访问 (状态码: $DOCS_RESPONSE)"
fi
echo ""

# 5. 检查 OpenAPI JSON
echo "5. 检查 OpenAPI JSON..."
OPENAPI_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/openapi.json")
if [ "$OPENAPI_RESPONSE" = "200" ]; then
    echo "   ✓ OpenAPI JSON 可访问 (状态码: $OPENAPI_RESPONSE)"
    echo "   检查是否包含 /api/v1/chargers 路由..."
    if curl -s "$API_BASE/openapi.json" | grep -q "/api/v1/chargers"; then
        echo "   ✓ 找到 /api/v1/chargers 路由定义"
    else
        echo "   ✗ 未找到 /api/v1/chargers 路由定义"
    fi
else
    echo "   ✗ OpenAPI JSON 不可访问 (状态码: $OPENAPI_RESPONSE)"
fi
echo ""

echo "=========================================="
echo "诊断完成"
echo "=========================================="
echo ""
echo "建议："
if [ "$V1_CHARGERS_RESPONSE" = "404" ]; then
    echo "1. 检查服务器日志，查看 API v1 路由是否成功注册"
    echo "2. 检查数据库连接是否正常"
    echo "3. 检查数据库表是否已初始化"
    echo "4. 如果使用旧版端点，可以临时使用 /chargers"
fi
