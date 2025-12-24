-- ============================================
-- 数据库迁移脚本
-- 1. 将 connector_type 从 charge_points 下放到 evses
-- 2. 修改 transaction_id 唯一性约束为组合唯一 (charge_point_id, evse_id, transaction_id)
-- ============================================
-- 使用方法:
--   docker exec -i ocpp-db-prod psql -U ocpp_user -d ocpp < migrate_connector_type_and_transaction_unique.sql
-- ============================================

BEGIN;

-- ============================================
-- 步骤1: 将 charge_points.connector_type 数据迁移到 evses.connector_type
-- ============================================
-- 如果 evses.connector_type 为空，则从 charge_points 复制
UPDATE evses
SET connector_type = (
    SELECT cp.connector_type
    FROM charge_points cp
    WHERE cp.id = evses.charge_point_id
)
WHERE connector_type IS NULL;

-- 如果 charge_points 有默认值但 evses 没有，设置默认值
UPDATE evses
SET connector_type = 'Type2'
WHERE connector_type IS NULL;

-- ============================================
-- 步骤2: 删除 charge_points 表的 connector_type 列
-- ============================================
ALTER TABLE charge_points DROP COLUMN IF EXISTS connector_type;

-- ============================================
-- 步骤3: 修改 evses.connector_type 为 NOT NULL 并设置默认值
-- ============================================
ALTER TABLE evses 
    ALTER COLUMN connector_type SET DEFAULT 'Type2',
    ALTER COLUMN connector_type SET NOT NULL;

-- ============================================
-- 步骤4: 删除旧的 transaction_id 索引（如果存在）
-- ============================================
-- 注意：PostgreSQL 不会自动删除唯一索引，需要手动删除
DROP INDEX IF EXISTS idx_sessions_transaction_id;
DROP INDEX IF EXISTS charging_sessions_transaction_id_key;
DROP INDEX IF EXISTS charging_sessions_transaction_id_idx;

-- ============================================
-- 步骤5: 添加新的组合唯一约束
-- ============================================
-- 先检查是否已存在相同的组合唯一约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'idx_sessions_transaction_unique'
        AND contype = 'u'
    ) THEN
        -- 创建组合唯一索引
        CREATE UNIQUE INDEX idx_sessions_transaction_unique 
        ON charging_sessions (charge_point_id, evse_id, transaction_id);
    END IF;
END $$;

COMMIT;

-- ============================================
-- 验证迁移结果
-- ============================================
-- 检查 charge_points 表是否还有 connector_type 列
SELECT 
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'charge_points' AND column_name = 'connector_type'
        ) THEN 'ERROR: charge_points.connector_type 仍然存在'
        ELSE 'OK: charge_points.connector_type 已删除'
    END as charge_points_check;

-- 检查 evses 表的 connector_type 列
SELECT 
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'evses' 
            AND column_name = 'connector_type' 
            AND is_nullable = 'NO'
        ) THEN 'OK: evses.connector_type 已设置为 NOT NULL'
        ELSE 'WARNING: evses.connector_type 可能未正确设置'
    END as evses_check;

-- 检查组合唯一约束
SELECT 
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'idx_sessions_transaction_unique'
            AND contype = 'u'
        ) THEN 'OK: 组合唯一约束已创建'
        ELSE 'ERROR: 组合唯一约束未创建'
    END as unique_constraint_check;

-- 显示约束详情
SELECT 
    conname as constraint_name,
    contype as constraint_type,
    pg_get_constraintdef(oid) as constraint_definition
FROM pg_constraint
WHERE conname = 'idx_sessions_transaction_unique';

