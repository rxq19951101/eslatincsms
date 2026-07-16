#!/usr/bin/env python3
"""创建或重置 App Store / Play 审核用 AppUser 账号（预充余额，无应用内支付）。

App Store Connect 审核备注建议示例：

  Demo account: review@eslatin.com.co / Review2026!
  The account has prepaid wallet balance. In-app payment is not enabled in this
  build; charging settles against the wallet. Scan a station QR (or use the
  provided test charger) to start/stop a session.

用法:
  DATABASE_URL=... REVIEW_BALANCE=50000 python scripts/create_app_review_account.py
"""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from app.core.auth import get_password_hash

EMAIL = os.environ.get("REVIEW_EMAIL", "review@eslatin.com.co")
PASSWORD = os.environ.get("REVIEW_PASSWORD", "Review2026!")
BALANCE = float(os.environ.get("REVIEW_BALANCE", "50000"))
FULL_NAME = os.environ.get("REVIEW_FULL_NAME", "App Review")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://local:local@localhost:5432/ocpp")


def main() -> None:
    engine = create_engine(DB_URL)
    pwd_hash = get_password_hash(PASSWORD)

    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM app_users WHERE email = :e"), {"e": EMAIL}).fetchone()
        if row:
            uid = row[0]
            conn.execute(
                text("""
                    UPDATE app_users SET
                      password_hash = :ph, full_name = :fn, balance = :bal,
                      status = 'active', email_verified = true, updated_at = NOW()
                    WHERE id = :id
                """),
                {"ph": pwd_hash, "fn": FULL_NAME, "bal": BALANCE, "id": uid},
            )
            print(f"Updated review account {EMAIL} (id={uid}), balance={BALANCE} COP")
        else:
            uid = str(uuid4())
            conn.execute(
                text("""
                    INSERT INTO app_users (id, email, full_name, password_hash, balance, status, email_verified, created_at, updated_at)
                    VALUES (:id, :email, :fn, :ph, :bal, 'active', true, NOW(), NOW())
                """),
                {"id": uid, "email": EMAIL, "fn": FULL_NAME, "ph": pwd_hash, "bal": BALANCE},
            )
            print(f"Created review account {EMAIL} (id={uid}), balance={BALANCE} COP")

    print(
        "\nApp Review notes:\n"
        f"  Email: {EMAIL}\n"
        f"  Password: {PASSWORD}\n"
        f"  Prepaid balance: {BALANCE} COP\n"
        "  In-app payment disabled; wallet topped up by operator.\n"
    )


if __name__ == "__main__":
    main()
