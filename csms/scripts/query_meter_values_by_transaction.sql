-- ============================================
-- 通过 transaction_id 查询计量值数据
-- ============================================
-- 使用方法:
--   方式1: 在 Docker 容器中执行（替换 1766476788 为实际的 transaction_id）
--     docker exec -i ocpp-db-prod psql -U ocpp_user -d ocpp_prod -c "
--       SELECT mv.*, cs.transaction_id, cs.charge_point_id 
--       FROM meter_values mv 
--       INNER JOIN charging_sessions cs ON mv.session_id = cs.id 
--       WHERE cs.transaction_id = 1766476788 
--       ORDER BY mv.timestamp ASC;"
--
--   方式2: 进入 psql 后执行（先修改下面的 transaction_id）
--     docker exec -it ocpp-db-prod psql -U ocpp_user -d ocpp_prod
--     然后复制下面的 SQL 并执行
-- ============================================

-- ============================================
-- 方式1: 查询所有计量值（完整信息）
-- 将 1766476788 替换为实际的 transaction_id
-- ============================================
SELECT 
    mv.id as meter_value_id,
    mv.session_id,
    cs.transaction_id,
    cs.charge_point_id,
    cs.id_tag,
    cs.start_time as session_start_time,
    cs.end_time as session_end_time,
    mv.connector_id,
    mv.timestamp,
    mv.value as value_wh,
    ROUND(mv.value / 1000.0, 2) as value_kwh,
    mv.sampled_value
FROM meter_values mv
INNER JOIN charging_sessions cs ON mv.session_id = cs.id
WHERE cs.transaction_id = 1766476788  -- 修改这里的 transaction_id
ORDER BY mv.timestamp ASC;

-- ============================================
-- 方式2: 统计信息（记录数、电量总和等）
-- ============================================
SELECT 
    cs.transaction_id,
    cs.charge_point_id,
    COUNT(mv.id) as meter_value_count,
    MIN(mv.timestamp) as first_reading_time,
    MAX(mv.timestamp) as last_reading_time,
    MIN(mv.value) as min_value_wh,
    MAX(mv.value) as max_value_wh,
    ROUND((MAX(mv.value) - MIN(mv.value)) / 1000.0, 2) as total_energy_kwh
FROM charging_sessions cs
LEFT JOIN meter_values mv ON mv.session_id = cs.id
WHERE cs.transaction_id = 1766476788  -- 修改这里的 transaction_id
GROUP BY cs.transaction_id, cs.charge_point_id;

-- ============================================
-- 方式3: 查询会话基本信息（不包含计量值）
-- ============================================
SELECT 
    cs.id as session_id,
    cs.transaction_id,
    cs.charge_point_id,
    cs.id_tag,
    cs.user_id,
    cs.start_time,
    cs.end_time,
    cs.meter_start,
    cs.meter_stop,
    ROUND((cs.meter_stop - cs.meter_start) / 1000.0, 2) as session_energy_kwh,
    cs.status,
    (SELECT COUNT(*) FROM meter_values WHERE session_id = cs.id) as meter_value_count
FROM charging_sessions cs
WHERE cs.transaction_id = 1766476788;  -- 修改这里的 transaction_id

-- ============================================
-- 方式4: 如果知道 session_id，直接查询计量值
-- ============================================
-- SELECT * FROM meter_values WHERE session_id = <session_id> ORDER BY timestamp ASC;

