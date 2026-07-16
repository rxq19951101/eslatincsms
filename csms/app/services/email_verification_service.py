#
# App 用户邮箱验证：6 位验证码 + 邮件内链接 token
#

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.database.models import AppUser
from app.services.email_service import send_user_email, smtp_configured

logger = get_logger("ocpp_csms")

CODE_TTL_HOURS = 24
RESEND_COOLDOWN_SECONDS = 60


def _hash_value(raw: str) -> str:
    pepper = get_settings().secret_key or "eslatin"
    return hashlib.sha256(f"{pepper}:{raw}".encode("utf-8")).hexdigest()


def _public_api_base() -> str:
    return (
        os.getenv("PUBLIC_API_BASE_URL", "").strip()
        or os.getenv("EXPO_PUBLIC_API_URL", "").strip()
        or "https://api.eslatin.com.co"
    ).rstrip("/")


def issue_email_verification(db: Session, user: AppUser) -> Tuple[str, str]:
    """生成并保存验证码/token，发邮件。返回 (code, token) 便于开发调试。"""
    code = f"{secrets.randbelow(1_000_000):06d}"
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    user.email_verification_code_hash = _hash_value(code)
    user.email_verification_token_hash = _hash_value(token)
    user.email_verification_expires_at = now + timedelta(hours=CODE_TTL_HOURS)
    user.email_verification_sent_at = now
    user.updated_at = now
    db.add(user)
    db.commit()
    db.refresh(user)

    verify_url = f"{_public_api_base()}/api/v1/app/auth/verify-email?token={token}"
    subject = "EsLatin — verifica tu correo / verify your email"
    text_body = (
        f"Hola {user.full_name or ''},\n\n"
        f"Tu código de verificación EsLatin es: {code}\n"
        f"También puedes abrir este enlace (válido {CODE_TTL_HOURS}h):\n"
        f"{verify_url}\n\n"
        f"Si no solicitaste esto, ignora este mensaje.\n"
    )
    html_body = f"""
    <p>Hola {user.full_name or ''},</p>
    <p>Tu código de verificación <strong>EsLatin</strong> es:</p>
    <p style="font-size:28px;letter-spacing:6px;font-weight:700;">{code}</p>
    <p>O abre este enlace (válido {CODE_TTL_HOURS} horas):</p>
    <p><a href="{verify_url}">{verify_url}</a></p>
    <p>Si no solicitaste esto, ignora este mensaje.</p>
    """

    sent = send_user_email(user.email, subject, text_body, html_body)
    if not sent:
        # 无 SMTP 时仍把验证码打进日志，方便本机/隧道联调
        logger.warning(
            "Email verification issued without SMTP delivery | email=%s | code=%s | url=%s",
            user.email,
            code,
            verify_url,
        )
    else:
        logger.info("Email verification issued | email=%s | smtp=ok", user.email)

    return code, token


def can_resend(user: AppUser) -> Tuple[bool, int]:
    """是否可重发；(allowed, seconds_remaining)。"""
    if not user.email_verification_sent_at:
        return True, 0
    sent = user.email_verification_sent_at
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - sent).total_seconds()
    if elapsed >= RESEND_COOLDOWN_SECONDS:
        return True, 0
    return False, int(RESEND_COOLDOWN_SECONDS - elapsed)


def verify_by_code(db: Session, email: str, code: str) -> Optional[AppUser]:
    user = db.query(AppUser).filter(AppUser.email == email.strip().lower()).first()
    if not user or not user.email_verification_code_hash or not user.email_verification_expires_at:
        return None
    exp = user.email_verification_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    if user.email_verification_code_hash != _hash_value(code.strip()):
        return None
    _mark_verified(db, user)
    return user


def verify_by_token(db: Session, token: str) -> Optional[AppUser]:
    if not token:
        return None
    token_hash = _hash_value(token.strip())
    user = (
        db.query(AppUser)
        .filter(AppUser.email_verification_token_hash == token_hash)
        .first()
    )
    if not user or not user.email_verification_expires_at:
        return None
    exp = user.email_verification_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    _mark_verified(db, user)
    return user


def _mark_verified(db: Session, user: AppUser) -> None:
    user.email_verified = True
    user.email_verification_code_hash = None
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)


def find_user_id_preview(user: AppUser) -> Optional[UUID]:
    return user.id if user else None
