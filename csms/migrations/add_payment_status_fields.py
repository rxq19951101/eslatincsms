"""
添加 charging_sessions.payment_status 与 app_users.has_unpaid_charges 字段。

执行：python migrations/add_payment_status_fields.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database.base import engine
from app.core.logging_config import get_logger

logger = get_logger("migration")


def migrate():
    logger.info("Starting migration: add payment status fields")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("""
                ALTER TABLE charging_sessions
                ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) DEFAULT 'pending';
            """))
            conn.execute(text("""
                ALTER TABLE charging_sessions
                ADD COLUMN IF NOT EXISTS payment_order_id UUID;
            """))
            conn.execute(text("""
                ALTER TABLE charging_sessions
                ADD COLUMN IF NOT EXISTS payment_deadline_at TIMESTAMPTZ;
            """))
            conn.execute(text("""
                ALTER TABLE app_users
                ADD COLUMN IF NOT EXISTS has_unpaid_charges BOOLEAN NOT NULL DEFAULT false;
            """))
            trans.commit()
            logger.info("Migration completed successfully")
        except Exception:
            trans.rollback()
            raise


if __name__ == "__main__":
    migrate()
