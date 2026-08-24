"""One-time password reset token issuance and consumption for AppUser."""

from __future__ import annotations

import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.database.models import AppUser
from app.services.email_service import send_user_email

logger = get_logger("ocpp_csms")
TOKEN_TTL_MINUTES = 30
REQUEST_COOLDOWN_SECONDS = 60
DEFAULT_LOCALE = "es"
SUPPORTED_LOCALES = frozenset({"es", "en", "zh"})

_EMAIL_COPY = {
    "es": {
        "lang": "es",
        "subject": "EsLatin — Restablece tu contraseña",
        "title": "Restablece tu contraseña",
        "intro": "Recibimos una solicitud para restablecer la contraseña de tu cuenta EsLatin.",
        "button": "Restablecer contraseña",
        "expiry": f"Este enlace vence en {TOKEN_TTL_MINUTES} minutos.",
        "security_title": "Aviso de seguridad",
        "security": "Si no solicitaste este cambio, ignora este mensaje. Tu contraseña seguirá siendo la misma.",
        "fallback": "Si el botón no funciona, copia y pega este enlace en tu navegador:",
        "footer": "Este es un mensaje automático de EsLatin.",
    },
    "en": {
        "lang": "en",
        "subject": "EsLatin — Reset your password",
        "title": "Reset your password",
        "intro": "We received a request to reset the password for your EsLatin account.",
        "button": "Reset password",
        "expiry": f"This link expires in {TOKEN_TTL_MINUTES} minutes.",
        "security_title": "Security notice",
        "security": "If you did not request this change, ignore this message. Your password will remain unchanged.",
        "fallback": "If the button does not work, copy and paste this link into your browser:",
        "footer": "This is an automated message from EsLatin.",
    },
    "zh": {
        "lang": "zh",
        "subject": "EsLatin — 重置你的密码",
        "title": "重置你的密码",
        "intro": "我们收到了重置你的 EsLatin 账户密码的请求。",
        "button": "重置密码",
        "expiry": f"此链接将在 {TOKEN_TTL_MINUTES} 分钟后失效。",
        "security_title": "安全提示",
        "security": "如果这不是你本人发起的请求，请忽略此邮件。你的密码不会被更改。",
        "fallback": "如果按钮无法打开，请复制以下链接并粘贴到浏览器中：",
        "footer": "这是一封由 EsLatin 自动发送的邮件。",
    },
}


def _hash_token(token: str) -> str:
    pepper = get_settings().secret_key or "eslatin"
    return hashlib.sha256(f"{pepper}:{token}".encode("utf-8")).hexdigest()


def _public_api_base() -> str:
    return (
        os.getenv("PUBLIC_API_BASE_URL", "").strip()
        or os.getenv("EXPO_PUBLIC_API_URL", "").strip()
        or "https://api.eslatin.com.co"
    ).rstrip("/")


def _reset_url(token: str, locale: Optional[str]) -> str:
    query = urlencode(
        {
            "token": token,
            "locale": _normalize_locale(locale),
        }
    )
    return f"{_public_api_base()}/api/v1/app/auth/reset-password/open?{query}"


def _normalize_locale(locale: Optional[str]) -> str:
    if not isinstance(locale, str):
        return DEFAULT_LOCALE
    normalized = locale.strip().lower()
    return normalized if normalized in SUPPORTED_LOCALES else DEFAULT_LOCALE


def _email_bodies(locale: Optional[str], reset_url: str) -> tuple[str, str, str]:
    copy = _EMAIL_COPY[_normalize_locale(locale)]
    text_body = (
        f"EsLatin\n\n{copy['title']}\n\n"
        f"{copy['intro']}\n\n"
        f"{copy['button']}:\n{reset_url}\n\n"
        f"{copy['expiry']}\n\n"
        f"{copy['security_title']}\n{copy['security']}\n\n"
        f"{copy['fallback']}\n{reset_url}\n\n"
        f"{copy['footer']}"
    )
    safe_url = html.escape(reset_url, quote=True)
    html_body = f"""<!doctype html>
<html lang="{copy['lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{copy['title']}</title>
  <style>
    @media only screen and (max-width: 620px) {{
      .email-card {{ width: 100% !important; }}
      .email-content {{ padding: 28px 22px !important; }}
      .action-button {{ display: block !important; width: 100% !important; box-sizing: border-box; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:#f3f6fa; color:#17233c; font-family:Arial, Helvetica, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%; background-color:#f3f6fa;">
    <tr>
      <td align="center" style="padding:32px 12px;">
        <table role="presentation" class="email-card" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%; max-width:600px; background-color:#ffffff; border-radius:14px; overflow:hidden;">
          <tr>
            <td style="padding:24px 32px; background-color:#123a72; color:#ffffff; font-size:26px; font-weight:700; letter-spacing:0.3px;">EsLatin</td>
          </tr>
          <tr>
            <td class="email-content" style="padding:38px 42px;">
              <h1 style="margin:0 0 18px; color:#17233c; font-size:28px; line-height:1.25;">{copy['title']}</h1>
              <p style="margin:0 0 26px; color:#45536c; font-size:16px; line-height:1.6;">{copy['intro']}</p>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px;">
                <tr>
                  <td align="center" bgcolor="#e65f2b" style="border-radius:8px;">
                    <a class="action-button" href="{safe_url}" style="display:inline-block; padding:14px 26px; color:#ffffff; font-size:16px; font-weight:700; line-height:1.2; text-decoration:none; border-radius:8px;">{copy['button']}</a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 26px; color:#45536c; font-size:15px; line-height:1.6;"><strong>{copy['expiry']}</strong></p>
              <div style="margin:0 0 26px; padding:18px; background-color:#f7f9fc; border-left:4px solid #123a72;">
                <p style="margin:0 0 6px; color:#17233c; font-size:15px; font-weight:700;">{copy['security_title']}</p>
                <p style="margin:0; color:#45536c; font-size:14px; line-height:1.55;">{copy['security']}</p>
              </div>
              <p style="margin:0 0 8px; color:#66738a; font-size:13px; line-height:1.5;">{copy['fallback']}</p>
              <p style="margin:0; overflow-wrap:anywhere; word-break:break-all; color:#123a72; font-size:13px; line-height:1.5;"><a href="{safe_url}" style="color:#123a72; text-decoration:underline;">{safe_url}</a></p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px; background-color:#eef3f9; color:#66738a; font-size:12px; line-height:1.5; text-align:center;">{copy['footer']}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return copy["subject"], text_body, html_body


def issue_password_reset(
    db: Session,
    user: AppUser,
    locale: Optional[str] = DEFAULT_LOCALE,
) -> None:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    user.password_reset_token_hash = _hash_token(token)
    user.password_reset_expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
    user.password_reset_requested_at = now
    user.updated_at = now
    db.add(user)
    db.commit()

    reset_url = _reset_url(token, locale)
    subject, text_body, html_body = _email_bodies(locale, reset_url)
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
