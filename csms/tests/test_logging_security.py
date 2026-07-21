"""SEC-LOG-001 regression coverage for pre-handler log redaction."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from app.core.api_logging import log_api_request
from app.core.log_sanitization import REDACTED, SensitiveDataFilter
from app.core.middleware import LoggingMiddleware
from app.core.observability import TraceMetricsMiddleware


_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)


def _serialize_application_records(records: list[logging.LogRecord]) -> str:
    serialized = []
    for record in records:
        serialized.append(
            {
                "message": record.getMessage(),
                "args": record.args,
                "extra": {
                    key: value
                    for key, value in record.__dict__.items()
                    if key not in _STANDARD_RECORD_FIELDS
                },
            }
        )
    return json.dumps(serialized, default=str, sort_keys=True, ensure_ascii=False)


def _assert_secret_absent(serialized: str, secret: str) -> None:
    assert secret not in serialized
    for prefix_length in (8, 12, 20):
        if len(secret) >= prefix_length:
            assert secret[:prefix_length] not in serialized


@pytest.fixture
def logging_client():
    app = FastAPI()
    app.add_middleware(TraceMetricsMiddleware)
    app.add_middleware(LoggingMiddleware)

    @app.get("/api/v1/app/charging/check")
    @app.get("/api/v1/app/charging/active")
    async def charging_log_probe(qr_token: str = Query(...)):
        return {"success": True}

    httpx_logger = logging.getLogger("httpx")
    redacting_filter = SensitiveDataFilter()
    httpx_logger.addFilter(redacting_filter)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        httpx_logger.removeFilter(redacting_filter)


@pytest.mark.parametrize("endpoint", ["check", "active"])
def test_charging_qr_query_and_authorization_are_redacted_in_all_log_fields(
    logging_client: TestClient,
    caplog: pytest.LogCaptureFixture,
    endpoint: str,
):
    qr_token = "QrSecretPrefix_7Yp2nL4wV9sC6kM3"
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJzdWIiOiJzZWMtbG9nLXVzZXIifQ."
        "SignatureSecretPart1234567890"
    )
    trace_id = f"sec-log-qr-{endpoint}"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ocpp_csms"):
        response = logging_client.get(
            f"/api/v1/app/charging/{endpoint}",
            params={"qr_token": qr_token},
            headers={
                "Authorization": f"Bearer {jwt}",
                "X-Trace-ID": trace_id,
            },
        )

    assert response.status_code == 200
    serialized = _serialize_application_records(caplog.records)
    _assert_secret_absent(serialized, qr_token)
    _assert_secret_absent(serialized, jwt)
    assert REDACTED in serialized
    assert f"/api/v1/app/charging/{endpoint}" in serialized
    assert '"status_code"' in serialized
    assert '"trace_id"' in serialized
    assert trace_id in serialized


def test_login_password_body_is_redacted_before_logging(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
):
    password = "PasswordSecretPrefix_8vT4mP2qN7wK"
    trace_id = "sec-log-login"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ocpp_csms"):
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "sec-log-missing-user", "password": password},
            headers={"X-Trace-ID": trace_id},
        )

    assert response.status_code == 401
    serialized = _serialize_application_records(caplog.records)
    _assert_secret_absent(serialized, password)
    assert REDACTED in serialized
    assert "/api/v1/admin/auth/login" in serialized
    assert '"status_code"' in serialized
    assert trace_id in serialized


def test_fake_payment_webhook_signature_and_secret_are_redacted(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    webhook_secret = "WebhookSecretPrefix_6rQ9cN2yH8mV"
    signature_value = "SignaturePrefix_5xL8pR3tW7kD"
    event_id = "sec-log-payment-event"
    trace_id = "sec-log-payment"
    monkeypatch.setenv("SIM_E2E_WEBHOOK_SECRET", webhook_secret)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ocpp_csms"):
        response = client.post(
            "/api/v1/app/wallet/payments/sim-webhook",
            json={
                "event_id": event_id,
                "provider": "fake",
                "status": "approved",
                "session_id": str(uuid4()),
                "webhook_secret": webhook_secret,
            },
            headers={
                "Idempotency-Key": event_id,
                "X-Sim-Signature": f"sha256={signature_value}",
                "X-Trace-ID": trace_id,
            },
        )

    assert response.status_code == 422
    serialized = _serialize_application_records(caplog.records)
    _assert_secret_absent(serialized, webhook_secret)
    _assert_secret_absent(serialized, signature_value)
    assert REDACTED in serialized
    assert "/api/v1/app/wallet/payments/sim-webhook" in serialized
    assert '"status_code"' in serialized
    assert trace_id in serialized


def test_api_logging_recursively_redacts_nested_values_and_prefixes(
    caplog: pytest.LogCaptureFixture,
):
    token = "ThirdPartyTokenPrefix_4nW8mK2xC9qR"
    password = "NestedPasswordPrefix_3vM7zQ5pL1sD"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ocpp_csms"):
        log_api_request(
            method="POST",
            path="/security/log-redaction",
            operation="redaction_test",
            params={
                "outer": [{"payment_token": token}],
                "credentials": {"password": password},
            },
        )

    serialized = _serialize_application_records(caplog.records)
    _assert_secret_absent(serialized, token)
    _assert_secret_absent(serialized, password)
    assert REDACTED in serialized
    assert "/security/log-redaction" in serialized
