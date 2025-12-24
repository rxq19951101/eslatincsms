#!/bin/bash
#
# 通过 transaction_id 查询计量值数据
# 使用方法: ./query_meter_values_by_transaction.sh <transaction_id> [container_name] [db_name] [db_user]
#

TRANSACTION_ID="${1:-1766476788}"
CONTAINER_NAME="${2:-ocpp-db-prod}"
DB_NAME="${3:-ocpp_prod}"
DB_USER="${4:-ocpp_user}"

echo "=========================================="
echo "查询计量值数据"
echo "=========================================="
echo "Transaction ID: $TRANSACTION_ID"
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

# 执行查询 SQL
echo "正在查询计量值数据..."
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" <<EOF
-- 方式1: 一条 SQL 查询所有计量值（推荐）
SELECT 
    mv.id,
    mv.session_id,
    cs.transaction_id,
    cs.charge_point_id,
    cs.id_tag,
    mv.connector_id,
    mv.timestamp,
    mv.value as value_wh,
    ROUND(mv.value / 1000.0, 2) as value_kwh,
    mv.sampled_value
FROM meter_values mv
INNER JOIN charging_sessions cs ON mv.session_id = cs.id
WHERE cs.transaction_id = $TRANSACTION_ID
ORDER BY mv.timestamp ASC;
EOF

echo ""
echo "=========================================="
echo "查询完成！"
echo "=========================================="

