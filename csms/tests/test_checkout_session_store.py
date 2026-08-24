"""PAY-MP-001 BE-2A encrypted Redis checkout storage tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from redis.exceptions import RedisError

from app.services.payment_checkout.crypto import PaymentTokenCipher
from app.services.payment_checkout.models import (
    CheckoutSessionRecord,
    CheckoutSessionStateError,
    CheckoutSessionStatus,
)
from app.services.payment_checkout.redis_store import (
    CheckoutIdempotencyConflict,
    CheckoutSessionCorrupt,
    CheckoutSessionNotFound,
    CheckoutSessionStore,
    CheckoutStoreUnavailable,
    CheckoutTokenUnavailable,
    CheckoutTransitionConflict,
)
from app.services.payment_providers.merchant_context import PaymentPurpose


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail = False
        self.cas_conflict = False

    def _check(self) -> None:
        if self.fail:
            raise RedisError("redis unavailable")

    def get(self, key):
        self._check()
        return self.values.get(key)

    def getdel(self, key):
        self._check()
        return self.values.pop(key, None)

    def set(self, key, value, *, ex=None, nx=False, xx=False):
        self._check()
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            if key in self.values:
                removed += 1
                del self.values[key]
        return removed

    def eval(self, script, numkeys, *args):
        self._check()
        if numkeys == 2:
            session_key, idempotency_key = args[:2]
            ciphertext, _ttl, index_value = args[2:]
            existing = self.values.get(idempotency_key)
            if existing is not None:
                return [1, existing]
            self.values[session_key] = ciphertext
            self.values[idempotency_key] = index_value
            return [0, index_value]
        if numkeys == 1:
            key = args[0]
            if len(args) == 4:
                _key, current, next_value, _ttl = args
                if key not in self.values:
                    return -1
                if self.cas_conflict or self.values[key] != current:
                    return 0
                self.values[key] = next_value
                return 1
            return self.values.pop(key, None)
        raise AssertionError("unexpected script")


@pytest.fixture
def checkout_store():
    client = FakeRedis()
    cipher = PaymentTokenCipher(Fernet.generate_key().decode("ascii"))
    return CheckoutSessionStore(
        redis_client=client,
        cipher=cipher,
        ttl_seconds=900,
    ), client


def _record(
    store: CheckoutSessionStore,
    *,
    opaque_id: str = "checkout_session_123456789",
    request: dict | None = None,
) -> CheckoutSessionRecord:
    now = datetime.now(timezone.utc)
    subject = request or {"purpose": "wallet_top_up", "amount": "50000.00"}
    return CheckoutSessionRecord(
        opaque_id=opaque_id,
        app_user_id=str(uuid4()),
        purpose=PaymentPurpose.WALLET_TOP_UP,
        status=CheckoutSessionStatus.CREATED,
        request_fingerprint=store.request_fingerprint(subject),
        created_at=now,
        expires_at=now + timedelta(minutes=15),
        data=subject,
    )


def test_session_state_is_encrypted_and_round_trips(checkout_store):
    store, client = checkout_store
    record = _record(store)

    result = store.save(record, idempotency_key="idem-secret-value")

    assert result.reused is False
    ciphertext = client.values[store._session_key(record.opaque_id)]
    assert record.app_user_id not in ciphertext
    assert "50000.00" not in ciphertext
    assert store.get(record.opaque_id) == record
    assert all("idem-secret-value" not in key for key in client.values)


def test_same_idempotency_request_reuses_original_session(checkout_store):
    store, _client = checkout_store
    first = _record(store, opaque_id="checkout_session_first_123")
    second = CheckoutSessionRecord(
        opaque_id="checkout_session_second_123",
        app_user_id=first.app_user_id,
        purpose=first.purpose,
        status=first.status,
        request_fingerprint=first.request_fingerprint,
        created_at=first.created_at,
        expires_at=first.expires_at,
        data=first.data,
    )

    store.save(first, idempotency_key="same-idempotency-key")
    reused = store.save(second, idempotency_key="same-idempotency-key")

    assert reused.reused is True
    assert reused.record.opaque_id == first.opaque_id

    looked_up = store.get_by_idempotency(
        app_user_id=first.app_user_id,
        idempotency_key="same-idempotency-key",
        request_fingerprint=first.request_fingerprint,
    )
    assert looked_up == first


def test_idempotency_key_conflict_fails_closed(checkout_store):
    store, _client = checkout_store
    first = _record(store, request={"amount": "1000.00"})
    second = CheckoutSessionRecord(
        opaque_id="checkout_session_conflict_123",
        app_user_id=first.app_user_id,
        purpose=first.purpose,
        status=first.status,
        request_fingerprint=store.request_fingerprint({"amount": "2000.00"}),
        created_at=first.created_at,
        expires_at=first.expires_at,
        data={"amount": "2000.00"},
    )
    store.save(first, idempotency_key="same-idempotency-key")

    with pytest.raises(CheckoutIdempotencyConflict):
        store.save(second, idempotency_key="same-idempotency-key")


def test_card_token_is_encrypted_and_consumed_once(checkout_store):
    store, client = checkout_store
    record = _record(store)
    store.save(record, idempotency_key="token-idempotency-key")
    card_token = "provider-card-token-secret"

    store.store_card_token(record.opaque_id, card_token)
    ciphertext = client.values[store._token_key(record.opaque_id)]
    assert card_token not in ciphertext
    assert store.consume_card_token(record.opaque_id) == card_token
    with pytest.raises(CheckoutTokenUnavailable):
        store.consume_card_token(record.opaque_id)


def test_tampered_state_and_redis_failure_fail_closed(checkout_store):
    store, client = checkout_store
    record = _record(store)
    store.save(record, idempotency_key="tamper-idempotency-key")
    client.values[store._session_key(record.opaque_id)] = "tampered-ciphertext"

    with pytest.raises(CheckoutSessionCorrupt):
        store.get(record.opaque_id)

    client.fail = True
    with pytest.raises(CheckoutStoreUnavailable):
        store.get(record.opaque_id)


def test_expired_session_and_invalid_state_transition_are_rejected(checkout_store):
    store, _client = checkout_store
    now = datetime.now(timezone.utc)
    expired = CheckoutSessionRecord(
        opaque_id="checkout_session_expired_123",
        app_user_id=str(uuid4()),
        purpose=PaymentPurpose.WALLET_TOP_UP,
        status=CheckoutSessionStatus.CREATED,
        request_fingerprint=store.request_fingerprint({"amount": "1000.00"}),
        created_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=5),
        data={"amount": "1000.00"},
    )
    with pytest.raises(CheckoutSessionNotFound):
        store.save(expired, idempotency_key="expired-idempotency-key")

    approved = _record(store).transition_to(CheckoutSessionStatus.READY)
    approved = approved.transition_to(CheckoutSessionStatus.PROCESSING)
    approved = approved.transition_to(CheckoutSessionStatus.APPROVED)
    with pytest.raises(CheckoutSessionStateError):
        approved.transition_to(CheckoutSessionStatus.PROCESSING)


def test_status_transition_uses_compare_and_set(checkout_store):
    store, client = checkout_store
    record = _record(store)
    store.save(record, idempotency_key="transition-idempotency-key")

    ready = store.transition(record.opaque_id, CheckoutSessionStatus.READY)
    assert ready.status is CheckoutSessionStatus.READY
    assert store.get(record.opaque_id).status is CheckoutSessionStatus.READY

    client.cas_conflict = True
    with pytest.raises(CheckoutTransitionConflict):
        store.transition(record.opaque_id, CheckoutSessionStatus.PROCESSING)


def test_sensitive_fields_cannot_enter_checkout_state(checkout_store):
    store, _client = checkout_store
    now = datetime.now(timezone.utc)
    with pytest.raises(CheckoutSessionStateError, match="Sensitive fields"):
        CheckoutSessionRecord(
            opaque_id="checkout_session_sensitive_123",
            app_user_id=str(uuid4()),
            purpose=PaymentPurpose.WALLET_TOP_UP,
            status=CheckoutSessionStatus.CREATED,
            request_fingerprint=store.request_fingerprint({"amount": "1000.00"}),
            created_at=now,
            expires_at=now + timedelta(minutes=15),
            data={"card_token": "must-not-be-stored"},
        )
