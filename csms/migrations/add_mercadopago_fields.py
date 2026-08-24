"""
数据库迁移脚本：添加 Mercado Pago 支付字段

执行方式：
python -c "from migrations.add_mercadopago_fields import migrate; migrate()"
或
python migrations/add_mercadopago_fields.py
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database.base import engine
from app.core.logging_config import get_logger

logger = get_logger("migration")


def migrate():
    """执行迁移"""
    logger.info("Starting migration: add Mercado Pago fields")
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # 1. 添加 payment_provider 字段到 payment_orders
            logger.info("Adding payment_provider column to payment_orders")
            conn.execute(text("""
                ALTER TABLE payment_orders 
                ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(50) DEFAULT 'wompi';
            """))
            
            # 2. 添加 external_reference 字段到 payment_orders
            logger.info("Adding external_reference column to payment_orders")
            conn.execute(text("""
                ALTER TABLE payment_orders 
                ADD COLUMN IF NOT EXISTS external_reference VARCHAR(128);
            """))
            
            # 3. 添加 mercadopago_payment_id 字段到 payment_orders
            logger.info("Adding mercadopago_payment_id column to payment_orders")
            conn.execute(text("""
                ALTER TABLE payment_orders 
                ADD COLUMN IF NOT EXISTS mercadopago_payment_id VARCHAR(255);
            """))
            
            # 4. 创建 external_reference 唯一索引
            logger.info("Creating unique index on external_reference")
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_external_reference 
                ON payment_orders(external_reference) 
                WHERE external_reference IS NOT NULL;
            """))
            
            # 5. 创建 mercadopago_payment_id 索引
            logger.info("Creating index on mercadopago_payment_id")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_payment_orders_mercadopago_payment_id 
                ON payment_orders(mercadopago_payment_id) 
                WHERE mercadopago_payment_id IS NOT NULL;
            """))
            
            # 6. 创建 payment_provider 索引
            logger.info("Creating index on payment_provider")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_payment_orders_provider 
                ON payment_orders(payment_provider);
            """))
            
            # 7. 修改 reference 字段为可空（因为 Mercado Pago 使用 external_reference）
            logger.info("Making reference column nullable")
            conn.execute(text("""
                ALTER TABLE payment_orders 
                ALTER COLUMN reference DROP NOT NULL;
            """))
            
            # 8. 添加 payment_provider 字段到 payment_webhook_events
            logger.info("Adding payment_provider column to payment_webhook_events")
            conn.execute(text("""
                ALTER TABLE payment_webhook_events 
                ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(50);
            """))
            
            # 9. 添加 payment_provider_id 字段到 payment_webhook_events
            logger.info("Adding payment_provider_id column to payment_webhook_events")
            conn.execute(text("""
                ALTER TABLE payment_webhook_events 
                ADD COLUMN IF NOT EXISTS payment_provider_id VARCHAR(255);
            """))
            
            # 10. 添加 event_id 字段到 payment_webhook_events
            logger.info("Adding event_id column to payment_webhook_events")
            conn.execute(text("""
                ALTER TABLE payment_webhook_events 
                ADD COLUMN IF NOT EXISTS event_id VARCHAR(255);
            """))
            
            # 11. 修改 wompi 字段为可空
            logger.info("Making Wompi fields nullable in payment_webhook_events")
            conn.execute(text("""
                ALTER TABLE payment_webhook_events 
                ALTER COLUMN wompi_transaction_id DROP NOT NULL;
            """))
            conn.execute(text("""
                ALTER TABLE payment_webhook_events 
                ALTER COLUMN wompi_event_id DROP NOT NULL;
            """))
            
            # 12. 创建通用 webhook 事件唯一约束
            logger.info("Creating unique constraint for generic webhook events")
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_webhook_event_generic 
                ON payment_webhook_events(payment_provider, payment_provider_id, event_id) 
                WHERE payment_provider IS NOT NULL 
                  AND payment_provider_id IS NOT NULL 
                  AND event_id IS NOT NULL;
            """))
            
            # 13. 创建 payment_provider 索引
            logger.info("Creating index on payment_provider in payment_webhook_events")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_webhook_events_provider 
                ON payment_webhook_events(payment_provider) 
                WHERE payment_provider IS NOT NULL;
            """))
            
            # 14. 创建 payment_provider_id 索引
            logger.info("Creating index on payment_provider_id in payment_webhook_events")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_id 
                ON payment_webhook_events(payment_provider_id) 
                WHERE payment_provider_id IS NOT NULL;
            """))
            
            trans.commit()
            logger.info("Migration completed successfully")
        except Exception as e:
            trans.rollback()
            logger.error(f"Migration failed: {str(e)}", exc_info=True)
            raise


if __name__ == "__main__":
    migrate()
