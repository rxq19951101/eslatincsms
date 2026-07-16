"""
为 app_users 增加邮箱验证码字段。

执行：python migrations/add_email_verification_fields.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database.base import engine
from app.core.logging_config import get_logger

logger = get_logger("migration")


def migrate():
    logger.info("Starting migration: add email verification fields")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for stmt in [
                "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verification_code_hash VARCHAR(64)",
                "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verification_token_hash VARCHAR(64)",
                "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ",
                "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMPTZ",
            ]:
                conn.execute(text(stmt))
            trans.commit()
            logger.info("Migration completed: email verification fields")
        except Exception:
            trans.rollback()
            raise


if __name__ == "__main__":
    migrate()
