"""Focused tests for APP-RECOVERY-001/002 password recovery."""

from datetime import timedelta
import html
import uuid
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest

from app.api.v1.app.auth import PasswordResetRequest
from app.core.auth import get_password_hash
from app.database.models import AppUser
from app.services import password_reset_service


@pytest.mark.parametrize(
    ("locale", "subject_text", "button_text", "expiry_text", "security_text", "fallback_text"),
    [
        ("es", "Restablece tu contraseña", "Restablecer contraseña", "30 minutos", "Aviso de seguridad", "copia y pega"),
        ("en", "Reset your password", "Reset password", "30 minutes", "Security notice", "copy and paste"),
        ("zh", "重置你的密码", "重置密码", "30 分钟", "安全提示", "复制以下链接"),
    ],
)
def test_issue_password_reset_sends_localized_plain_and_branded_html(
    monkeypatch,
    locale,
    subject_text,
    button_text,
    expiry_text,
    security_text,
    fallback_text,
):
    db = MagicMock()
    user = AppUser(
        id=uuid.uuid4(),
        email=f"recovery-{locale}@example.test",
        password_hash="existing-password-hash",
    )
    delivered = {}

    monkeypatch.setattr(password_reset_service.secrets, "token_urlsafe", lambda _: "fixed-reset-token")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://recovery.example.test/")

    def capture_email(to_addr, subject, text_body, html_body):
        delivered.update(
            to_addr=to_addr,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        return True

    monkeypatch.setattr(password_reset_service, "send_user_email", capture_email)

    password_reset_service.issue_password_reset(db, user, locale=locale)

    reset_url = (
        "https://recovery.example.test/api/v1/app/auth/reset-password/open?"
        + urlencode({"token": "fixed-reset-token", "locale": locale})
    )
    assert delivered["to_addr"] == user.email
    assert subject_text in delivered["subject"]
    assert button_text in delivered["text_body"]
    assert expiry_text in delivered["text_body"]
    assert security_text in delivered["text_body"]
    assert fallback_text in delivered["text_body"]
    assert reset_url in delivered["text_body"]
    assert "eslatin://" not in delivered["text_body"]

    html_body = delivered["html_body"]
    assert f'<html lang="{locale}">' in html_body
    assert "EsLatin" in html_body
    assert button_text in html_body
    assert expiry_text in html_body
    assert security_text in html_body
    assert fallback_text in html_body
    assert reset_url in html.unescape(html_body)
    assert "eslatin://" not in html_body
    assert "max-width:600px" in html_body
    assert "<script" not in html_body.lower()
    assert "@import" not in html_body.lower()
    assert "font-face" not in html_body.lower()
    assert "<link" not in html_body.lower()

    assert user.password_reset_token_hash
    assert user.password_reset_expires_at - user.password_reset_requested_at == timedelta(minutes=30)
    db.add.assert_called_once_with(user)
    db.commit.assert_called_once_with()


def test_password_reset_email_url_encodes_token_and_normalized_locale(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test/root/")
    token = 'token /+?&=<script>alert("token")</script>'

    reset_url = password_reset_service._reset_url(token, " EN ")

    assert reset_url == (
        "https://api.example.test/root/api/v1/app/auth/reset-password/open?"
        + urlencode({"token": token, "locale": "en"})
    )
    assert token not in reset_url
    assert "<script>" not in reset_url


@pytest.mark.parametrize(
    ("payload", "expected_locale"),
    [
        ({"email": "old-client@example.test"}, "es"),
        ({"email": "null-locale@example.test", "locale": None}, "es"),
        ({"email": "invalid@example.test", "locale": '<script>alert("x")</script>'}, "es"),
        ({"email": "english@example.test", "locale": " EN "}, "en"),
        ({"email": "chinese@example.test", "locale": "zh"}, "zh"),
    ],
)
def test_password_reset_request_normalizes_locale(payload, expected_locale):
    request = PasswordResetRequest.model_validate(payload)
    assert request.locale == expected_locale


def test_invalid_service_locale_falls_back_to_spanish_without_template_injection(monkeypatch):
    db = MagicMock()
    user = AppUser(
        id=uuid.uuid4(),
        email="invalid-locale@example.test",
        password_hash="existing-password-hash",
    )
    delivered = {}
    malicious_locale = '<script>alert("locale")</script>'

    monkeypatch.setattr(password_reset_service.secrets, "token_urlsafe", lambda _: "fixed-reset-token")

    def capture_email(to_addr, subject, text_body, html_body):
        delivered.update(subject=subject, text_body=text_body, html_body=html_body)
        return True

    monkeypatch.setattr(password_reset_service, "send_user_email", capture_email)

    password_reset_service.issue_password_reset(db, user, locale=malicious_locale)

    assert "Restablece tu contraseña" in delivered["subject"]
    assert "Restablecer contraseña" in delivered["html_body"]
    assert malicious_locale not in delivered["text_body"]
    assert malicious_locale not in delivered["html_body"]


@pytest.mark.parametrize(
    ("request_body", "expected_locale"),
    [
        ({"email": "recovery-api@example.test", "locale": "en"}, "en"),
        ({"email": "recovery-api@example.test"}, "es"),
        ({"email": "recovery-api@example.test", "locale": "unsupported"}, "es"),
    ],
)
def test_reset_password_api_passes_normalized_locale(
    client,
    db_session,
    request_body,
    expected_locale,
):
    user = AppUser(
        id=uuid.uuid4(),
        email="recovery-api@example.test",
        password_hash=get_password_hash("existing-password"),
        email_verified=True,
        status="active",
    )
    db_session.add(user)
    db_session.commit()

    with patch("app.api.v1.app.auth.issue_password_reset") as issue_reset:
        response = client.post("/api/v1/app/auth/reset-password", json=request_body)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "If the email exists, a reset link was sent.",
    }
    issue_reset.assert_called_once()
    assert issue_reset.call_args.args[1].id == user.id
    assert issue_reset.call_args.kwargs == {"locale": expected_locale}


@pytest.mark.parametrize(
    ("locale", "title", "button"),
    [
        ("es", "Restablece tu contraseña", "Abrir EsLatin"),
        ("en", "Reset your password", "Open EsLatin"),
        ("zh", "重置你的密码", "打开 EsLatin"),
    ],
)
def test_password_reset_open_page_is_localized_and_links_to_app_without_consuming_token(
    client,
    locale,
    title,
    button,
):
    token = "reset token/+?&=safe"
    deep_link = f"eslatin://reset-password?{urlencode({'token': token})}"

    with patch("app.api.v1.app.auth.consume_password_reset_token") as consume_token:
        response = client.get(
            "/api/v1/app/auth/reset-password/open",
            params={"token": token, "locale": locale},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f'<html lang="{locale}">' in response.text
    assert title in response.text
    assert button in response.text
    assert f'href="{deep_link}"' in response.text
    assert token not in response.text
    consume_token.assert_not_called()

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'none'" in csp


def test_password_reset_open_page_escapes_malicious_token_and_falls_back_to_spanish(
    client,
):
    token = '"><script>alert("token")</script>&next=https://evil.test'
    locale = '<img src=x onerror="alert(locale)">'
    encoded_deep_link = f"eslatin://reset-password?{urlencode({'token': token})}"

    response = client.get(
        "/api/v1/app/auth/reset-password/open",
        params={"token": token, "locale": locale},
    )

    assert response.status_code == 200
    assert '<html lang="es">' in response.text
    assert "Restablece tu contraseña" in response.text
    assert f'href="{encoded_deep_link}"' in response.text
    assert token not in response.text
    assert locale not in response.text
    assert "<script>" not in response.text.lower()
    assert "<img" not in response.text.lower()
