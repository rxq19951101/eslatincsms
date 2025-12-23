-- 在 Docker 容器中删除充电桩信息的 SQL 脚本
-- 充电桩ID: 861076087029615

BEGIN;

-- 删除所有关联数据
DELETE FROM meter_values 
WHERE session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '861076087029615'
);

DELETE FROM invoices 
WHERE order_id IN (
    SELECT id FROM orders WHERE charge_point_id = '861076087029615'
) OR session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '861076087029615'
);

DELETE FROM orders 
WHERE charge_point_id = '861076087029615';

DELETE FROM charging_sessions 
WHERE charge_point_id = '861076087029615';

DELETE FROM evse_status 
WHERE charge_point_id = '861076087029615';

DELETE FROM evses 
WHERE charge_point_id = '861076087029615';

DELETE FROM charge_point_configs 
WHERE charge_point_id = '861076087029615';

DELETE FROM device_events 
WHERE charge_point_id = '861076087029615';

-- 最后删除充电桩
DELETE FROM charge_points 
WHERE id = '861076087029615';

COMMIT;

-- 验证设备是否保留
SELECT 
    serial_number,
    type_code,
    mqtt_client_id,
    is_active,
    '设备信息已保留' as status
FROM devices 
WHERE serial_number = '861076087029615';

