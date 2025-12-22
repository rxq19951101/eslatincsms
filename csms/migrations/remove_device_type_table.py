#!/usr/bin/env python3
"""
数据库迁移脚本：删除DeviceType表，将master_secret迁移到Device表
每个设备独立存储master_secret

使用方法：
    python migrations/remove_device_type_table.py
"""

import sys
import os
from sqlalchemy import text
from sqlalchemy.orm import Session

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.base import SessionLocal, engine


def migrate():
    """执行迁移"""
    print("=" * 60)
    print("开始迁移：删除DeviceType表，将master_secret迁移到Device表")
    print("=" * 60)
    
    db: Session = SessionLocal()
    try:
        # 检查devices表是否存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'devices'
            )
        """))
        if not result.scalar():
            print("❌ devices表不存在，请先初始化数据库")
            return False
        
        # 检查device_types表是否存在
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'device_types'
            )
        """))
        device_types_exists = result.scalar()
        
        if not device_types_exists:
            print("⚠️  device_types表不存在，可能已经迁移过")
            # 检查devices表是否已有新字段
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'devices' 
                AND column_name IN ('type_code', 'master_secret_encrypted')
            """))
            columns = [row[0] for row in result.fetchall()]
            if 'type_code' in columns and 'master_secret_encrypted' in columns:
                print("✓ devices表已包含新字段，迁移可能已完成")
                return True
            else:
                print("❌ devices表缺少新字段，请检查数据库结构")
                return False
        
        print("\n[1/8] 添加新字段到devices表...")
        db.execute(text("""
            ALTER TABLE devices 
            ADD COLUMN IF NOT EXISTS type_code VARCHAR(50) DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS master_secret_encrypted TEXT,
            ADD COLUMN IF NOT EXISTS encryption_algorithm VARCHAR(50) DEFAULT 'AES-256-GCM'
        """))
        db.commit()
        print("✓ 新字段已添加")
        
        print("\n[2/8] 迁移数据...")
        # 迁移数据
        db.execute(text("""
            UPDATE devices d
            SET 
                type_code = COALESCE(
                    (SELECT dt.type_code FROM device_types dt WHERE dt.id = d.device_type_id),
                    'default'
                ),
                master_secret_encrypted = COALESCE(
                    (SELECT dt.master_secret_encrypted FROM device_types dt WHERE dt.id = d.device_type_id),
                    encode(sha256(('default_secret_' || d.serial_number)::bytea), 'hex')
                ),
                encryption_algorithm = COALESCE(
                    (SELECT dt.encryption_algorithm FROM device_types dt WHERE dt.id = d.device_type_id),
                    'AES-256-GCM'
                )
            WHERE d.device_type_id IS NOT NULL
        """))
        db.commit()
        print("✓ 数据已迁移")
        
        print("\n[3/8] 为没有device_type_id的设备设置默认值...")
        db.execute(text("""
            UPDATE devices
            SET 
                type_code = 'default',
                master_secret_encrypted = encode(sha256(('default_secret_' || serial_number)::bytea), 'hex'),
                encryption_algorithm = 'AES-256-GCM'
            WHERE master_secret_encrypted IS NULL
        """))
        db.commit()
        print("✓ 默认值已设置")
        
        print("\n[4/8] 设置新字段为NOT NULL...")
        db.execute(text("""
            ALTER TABLE devices 
            ALTER COLUMN type_code SET NOT NULL,
            ALTER COLUMN master_secret_encrypted SET NOT NULL,
            ALTER COLUMN encryption_algorithm SET NOT NULL
        """))
        db.commit()
        print("✓ 字段约束已设置")
        
        print("\n[5/8] 删除外键约束...")
        db.execute(text("""
            ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_device_type_id_fkey
        """))
        db.commit()
        print("✓ 外键约束已删除")
        
        print("\n[6/8] 删除device_type_id列...")
        db.execute(text("""
            ALTER TABLE devices DROP COLUMN IF EXISTS device_type_id
        """))
        db.commit()
        print("✓ device_type_id列已删除")
        
        print("\n[7/8] 创建索引...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_devices_type_code ON devices(type_code)
        """))
        db.commit()
        print("✓ 索引已创建")
        
        print("\n[8/8] 删除device_types表...")
        db.execute(text("DROP TABLE IF EXISTS device_types CASCADE"))
        db.commit()
        print("✓ device_types表已删除")
        
        # 验证迁移结果
        print("\n验证迁移结果...")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total_devices,
                COUNT(DISTINCT type_code) as unique_type_codes,
                COUNT(*) FILTER (WHERE master_secret_encrypted IS NOT NULL) as devices_with_secret
            FROM devices
        """))
        row = result.fetchone()
        print(f"✓ 设备总数: {row[0]}")
        print(f"✓ 唯一类型代码数: {row[1]}")
        print(f"✓ 有master_secret的设备数: {row[2]}")
        
        print("\n" + "=" * 60)
        print("✓ 迁移完成！")
        print("=" * 60)
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)

