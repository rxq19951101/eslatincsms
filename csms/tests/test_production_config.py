from app.core.config import Settings


def test_documentation_urls_accept_disabled_sentinels(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "test-production-salt")
    monkeypatch.setenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true")

    settings = Settings(
        environment="production",
        secret_key="production-test-secret-key-with-32-characters",
        docs_url="None",
        redoc_url="off",
    )

    assert settings.docs_url is None
    assert settings.redoc_url is None
