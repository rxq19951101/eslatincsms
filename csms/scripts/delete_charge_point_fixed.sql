-- 修正版：正确的删除顺序
-- 先删除引用 evses 的 device_events，再删除 evses

BEGIN;

-- 1. 删除 MeterValue（关联到 ChargingSession）
DELETE FROM meter_values 
WHERE session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '861076087029615'
);

-- 2. 删除 Invoice（关联到 Order 和 ChargingSession）
DELETE FROM invoices 
WHERE order_id IN (
    SELECT id FROM orders WHERE charge_point_id = '861076087029615'
) OR session_id IN (
    SELECT id FROM charging_sessions WHERE charge_point_id = '861076087029615'
);

-- 3. 删除 Order（关联到 ChargingSession 和 ChargePoint）
DELETE FROM orders 
WHERE charge_point_id = '861076087029615';

-- 4. 删除 ChargingSession（关联到 EVSE 和 ChargePoint）
DELETE FROM charging_sessions 
WHERE charge_point_id = '861076087029615';

-- 5. 删除 EVSEStatus（关联到 EVSE 和 ChargePoint）
DELETE FROM evse_status 
WHERE charge_point_id = '861076087029615';

-- 6. 删除 DeviceEvent（关联到 EVSE 的）- 必须在删除 EVSE 之前
DELETE FROM device_events 
WHERE evse_id IN (
    SELECT id FROM evses WHERE charge_point_id = '861076087029615'
);

-- 7. 删除 DeviceEvent（关联到 ChargePoint 的）
DELETE FROM device_events 
WHERE charge_point_id = '861076087029615';

-- 8. 删除 EVSE（关联到 ChargePoint）- 现在可以安全删除了
DELETE FROM evses 
WHERE charge_point_id = '861076087029615';

-- 9. 删除 ChargePointConfig（关联到 ChargePoint）
DELETE FROM charge_point_configs 
WHERE charge_point_id = '861076087029615';

-- 10. 最后删除 ChargePoint
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

