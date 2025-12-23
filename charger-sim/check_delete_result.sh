#!/bin/bash
#
# 检查充电桩删除结果的脚本
#

SERVER="${1:-http://47.236.134.99:9000}"
CHARGE_POINT_ID="${2:-861076087029615}"
DEVICE_SERIAL="${3:-861076087029615}"

echo "=========================================="
echo "检查删除结果"
echo "=========================================="
echo "服务器: $SERVER"
echo "充电桩ID: $CHARGE_POINT_ID"
echo "设备序列号: $DEVICE_SERIAL"
echo "=========================================="
echo ""

# 1. 检查充电桩是否已删除
echo "1. 检查充电桩是否已删除:"
echo "   GET $SERVER/api/v1/chargers/$CHARGE_POINT_ID"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$SERVER/api/v1/chargers/$CHARGE_POINT_ID")
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

if [ "$HTTP_CODE" = "404" ]; then
    echo "   ✓ 充电桩已删除 (HTTP 404)"
elif [ "$HTTP_CODE" = "200" ]; then
    echo "   ✗ 充电桩仍然存在 (HTTP 200)"
    echo "   响应: $BODY"
else
    echo "   ? 未知状态 (HTTP $HTTP_CODE)"
    echo "   响应: $BODY"
fi
echo ""

# 2. 检查充电桩列表中是否还有该充电桩
echo "2. 检查充电桩列表中是否还有该充电桩:"
echo "   GET $SERVER/api/v1/chargers"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$SERVER/api/v1/chargers")
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

if echo "$BODY" | grep -q "\"id\":\"$CHARGE_POINT_ID\"" || echo "$BODY" | grep -q "\"id\": \"$CHARGE_POINT_ID\""; then
    echo "   ✗ 充电桩仍在列表中"
    echo "   找到的充电桩ID:"
    echo "$BODY" | grep -o "\"id\":\"[^\"]*\"" | head -5
else
    echo "   ✓ 充电桩不在列表中"
    CHARGE_POINT_COUNT=$(echo "$BODY" | grep -o "\"id\"" | wc -l)
    echo "   当前充电桩总数: $CHARGE_POINT_COUNT"
fi
echo ""

# 3. 检查设备是否保留
echo "3. 检查设备是否保留:"
echo "   GET $SERVER/api/v1/devices/$DEVICE_SERIAL"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$SERVER/api/v1/devices/$DEVICE_SERIAL")
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ 设备信息已保留 (HTTP 200)"
    echo "   设备信息:"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
elif [ "$HTTP_CODE" = "404" ]; then
    echo "   ✗ 设备信息不存在 (HTTP 404)"
else
    echo "   ? 未知状态 (HTTP $HTTP_CODE)"
    echo "   响应: $BODY"
fi
echo ""

# 4. 检查设备列表中是否还有该设备
echo "4. 检查设备列表中是否还有该设备:"
echo "   GET $SERVER/api/v1/devices"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$SERVER/api/v1/devices")
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

if echo "$BODY" | grep -q "\"serial_number\":\"$DEVICE_SERIAL\"" || echo "$BODY" | grep -q "\"serial_number\": \"$DEVICE_SERIAL\""; then
    echo "   ✓ 设备仍在列表中"
    DEVICE_COUNT=$(echo "$BODY" | grep -o "\"serial_number\"" | wc -l)
    echo "   当前设备总数: $DEVICE_COUNT"
else
    echo "   ✗ 设备不在列表中"
fi
echo ""

echo "=========================================="
echo "检查完成"
echo "=========================================="

