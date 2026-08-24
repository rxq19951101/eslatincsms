from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_bootstrap_uses_configured_email_accounts():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    initializer = (ROOT / "csms/scripts/create_initial_data.py").read_text(
        encoding="utf-8"
    )

    for key, email in (
        ("CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL", "support@eslatin.com.co"),
        ("CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL", "amos.ran@eslatin.com.co"),
    ):
        assert key in compose
        assert f"{key}={email}" in example
        assert key in initializer

    assert '"username": super_admin_email' in initializer
    assert '"username": tenant_admin_email' in initializer
    assert "admin@example.com" not in initializer
    assert "tenant_admin@example.com" not in initializer


def test_spacemail_uses_implicit_ssl_contract():
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    notifications = (ROOT / "csms/app/services/notification_service.py").read_text(
        encoding="utf-8"
    )

    assert "SMTP_HOST=mail.spacemail.com" in example
    assert "SMTP_PORT=465" in example
    assert "SMTP_USER=support@eslatin.com.co" in example
    assert "SMTP_SSL=true" in example
    assert "SMTP_TLS=false" in example
    assert "smtplib.SMTP_SSL" in notifications
