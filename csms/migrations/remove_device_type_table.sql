-- 迁移脚本：删除DeviceType表，将master_secret迁移到Device表
-- 执行前请备份数据库！

BEGIN;

-- 步骤1: 为Device表添加新字段
ALTER TABLE devices 
ADD COLUMN IF NOT EXISTS type_code VARCHAR(50) DEFAULT 'default',
ADD COLUMN IF NOT EXISTS master_secret_encrypted TEXT,
ADD COLUMN IF NOT EXISTS encryption_algorithm VARCHAR(50) DEFAULT 'AES-256-GCM';

-- 步骤2: 迁移数据（如果device_types表中有数据）
-- 将device_types的master_secret迁移到devices表
UPDATE devices d
SET 
    type_code = COALESCE(
        (SELECT dt.type_code FROM device_types dt WHERE dt.id = d.device_type_id),
        'default'
    ),
    master_secret_encrypted = COALESCE(
        (SELECT dt.master_secret_encrypted FROM device_types dt WHERE dt.id = d.device_type_id),
        -- 如果没有对应的device_type，生成默认的加密secret
        encode(sha256(('default_secret_' || d.serial_number)::bytea), 'hex')
    ),
    encryption_algorithm = COALESCE(
        (SELECT dt.encryption_algorithm FROM device_types dt WHERE dt.id = d.device_type_id),
        'AES-256-GCM'
    )
WHERE d.device_type_id IS NOT NULL;

-- 步骤3: 为没有device_type_id的设备设置默认值
UPDATE devices
SET 
    type_code = 'default',
    master_secret_encrypted = encode(sha256(('default_secret_' || serial_number)::bytea), 'hex'),
    encryption_algorithm = 'AES-256-GCM'
WHERE master_secret_encrypted IS NULL;

-- 步骤4: 设置新字段为NOT NULL（在数据迁移完成后）
ALTER TABLE devices 
ALTER COLUMN type_code SET NOT NULL,
ALTER COLUMN master_secret_encrypted SET NOT NULL,
ALTER COLUMN encryption_algorithm SET NOT NULL;

-- 步骤5: 删除外键约束
ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_device_type_id_fkey;

-- 步骤6: 删除device_type_id列
ALTER TABLE devices DROP COLUMN IF EXISTS device_type_id;

-- 步骤7: 创建索引
CREATE INDEX IF NOT EXISTS idx_devices_type_code ON devices(type_code);

-- 步骤8: 删除device_types表
DROP TABLE IF EXISTS device_types CASCADE;

COMMIT;

-- 验证迁移结果
SELECT 
    COUNT(*) as total_devices,
    COUNT(DISTINCT type_code) as unique_type_codes,
    COUNT(*) FILTER (WHERE master_secret_encrypted IS NOT NULL) as devices_with_secret
FROM devices;

