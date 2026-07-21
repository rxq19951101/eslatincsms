"""One-time password reset token issuance and consumption for AppUser."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.database.models import AppUser
from app.services.email_service import send_user_email

logger = get_logger("ocpp_csms")
TOKEN_TTL_MINUTES = 30
REQUEST_COOLDOWN_SECONDS = 60


def _hash_token(token: str) -> str:
    pepper = get_settings().secret_key or "eslatin"
    return hashlib.sha256(f"{pepper}:{token}".encode("utf-8")).hexdigest()


def _reset_url(token: str) -> str:
    scheme = os.getenv("APP_DEEP_LINK_SCHEME", "eslatin").strip() or "eslatin"
    return f"{scheme}://reset-password?token={token}"


def issue_password_reset(db: Session, user: AppUser) -> None:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    user.password_reset_token_hash = _hash_token(token)
    user.password_reset_expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
    user.password_reset_requested_at = now
    user.updated_at = now
    db.add(user)
    db.commit()

    reset_url = _reset_url(token)
    subject = "EsLatin — reset your password"
    text_body = (
        "We received a request to reset your EsLatin password.\n\n"
        f"Open this link within {TOKEN_TTL_MINUTES} minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = (
        "<p>We received a request to reset your EsLatin password.</p>"
        f"<p><a href=\"{reset_url}\">Reset your password</a> "
        f"(valid for {TOKEN_TTL_MINUTES} minutes).</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    sent = send_user_email(user.email, subject, text_body, html_body)
    if not sent:
        logger.warning(
            "Account recovery issued without SMTP delivery | email=%s",
            user.email,
        )


def can_request_password_reset(user: AppUser) -> tuple[bool, int]:
    sent_at = user.password_reset_requested_at
    if not sent_at:
        return True, 0
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
    if elapsed >= REQUEST_COOLDOWN_SECONDS:
        return True, 0
    return False, int(REQUEST_COOLDOWN_SECONDS - elapsed)


def consume_password_reset_token(
    db: Session, token: str, new_password_hash: str
) -> Optional[AppUser]:
    if not token:
        return None
    user = (
        db.query(AppUser)
        .filter(AppUser.password_reset_token_hash == _hash_token(token.strip()))
        .with_for_update()
        .first()
    )
    if not user or not user.password_reset_expires_at:
        return None
    expires_at = user.password_reset_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None

    user.password_hash = new_password_hash
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.password_reset_requested_at = None
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
