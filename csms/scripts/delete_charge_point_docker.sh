#!/bin/bash
#
# 在 Docker 容器中删除充电桩信息的脚本
# 使用方法: ./delete_charge_point_docker.sh <charge_point_id> [container_name] [db_name] [db_user]
#

CHARGE_POINT_ID="${1:-861076087029615}"
CONTAINER_NAME="${2:-ocpp-db-prod}"
DB_NAME="${3:-ocpp_prod}"
DB_USER="${4:-ocpp_user}"

echo "=========================================="
echo "删除充电桩信息（保留设备信息）"
echo "=========================================="
echo "充电桩ID: $CHARGE_POINT_ID"
echo "容器名: $CONTAINER_NAME"
echo "数据库名: $DB_NAME"
echo "数据库用户: $DB_USER"
echo "=========================================="
echo ""

# 检查容器是否存在
if ! docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "错误: 容器 '$CONTAINER_NAME' 不存在或未运行"
    echo ""
    echo "可用的数据库容器:"
    docker ps --format "{{.Names}}" | grep -E "(db|postgres|ocpp)"
    exit 1
fi

# 执行删除 SQL
echo "正在执行删除操作..."
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" <<EOF
BEGIN;

-- 删除所有关联数据
DELETE FROM meter_values 
WHERE session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '$CHARGE_POINT_ID'
);

DELETE FROM invoices 
WHERE order_id IN (
    SELECT id FROM orders WHERE charge_point_id = '$CHARGE_POINT_ID'
) OR session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '$CHARGE_POINT_ID'
);

DELETE FROM orders 
WHERE charge_point_id = '$CHARGE_POINT_ID';

DELETE FROM charging_sessions 
WHERE charge_point_id = '$CHARGE_POINT_ID';

DELETE FROM evse_status 
WHERE charge_point_id = '$CHARGE_POINT_ID';

DELETE FROM evses 
WHERE charge_point_id = '$CHARGE_POINT_ID';

DELETE FROM charge_point_configs 
WHERE charge_point_id = '$CHARGE_POINT_ID';

DELETE FROM device_events 
WHERE charge_point_id = '$CHARGE_POINT_ID';

-- 最后删除充电桩
DELETE FROM charge_points 
WHERE id = '$CHARGE_POINT_ID';

COMMIT;

-- 验证设备是否保留
SELECT 
    serial_number,
    type_code,
    mqtt_client_id,
    is_active,
    '设备信息已保留' as status
FROM devices 
WHERE serial_number = '$CHARGE_POINT_ID';
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ 删除完成！"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "✗ 删除失败，请检查错误信息"
    echo "=========================================="
    exit 1
fi

