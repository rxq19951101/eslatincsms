"""Fail-closed Redis repository for encrypted checkout session state."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping

import redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.services.payment_checkout.crypto import (
    PaymentTokenCipher,
    PaymentTokenCryptoError,
)
from app.services.payment_checkout.models import (
    CheckoutSessionRecord,
    CheckoutSessionStateError,
    CheckoutSessionStatus,
)


class CheckoutStoreError(RuntimeError):
    """Base safe error for checkout persistence failures."""


class CheckoutStoreUnavailable(CheckoutStoreError):
    pass


class CheckoutSessionNotFound(CheckoutStoreError):
    pass


class CheckoutSessionCorrupt(CheckoutStoreError):
    pass


class CheckoutIdempotencyConflict(CheckoutStoreError):
    pass


class CheckoutTransitionConflict(CheckoutStoreError):
    pass


class CheckoutTokenUnavailable(CheckoutStoreError):
    pass


class CheckoutTokenAlreadyStored(CheckoutStoreError):
    pass


@dataclass(frozen=True)
class CheckoutSaveResult:
    record: CheckoutSessionRecord
    reused: bool


class CheckoutSessionStore:
    SESSION_PREFIX = "pay:checkout:v1"
    IDEMPOTENCY_PREFIX = "pay:checkout-idem:v1"
    TOKEN_PREFIX = "pay:checkout-token:v1"

    _SAVE_SCRIPT = """
local existing = redis.call('GET', KEYS[2])
if existing then
  return {1, existing}
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[2])
return {0, ARGV[3]}
"""
    _TRANSITION_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return -1
end
if current ~= ARGV[1] then
  return 0
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3], 'XX')
return 1
"""
    _GET_DELETE_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then
  redis.call('DEL', KEYS[1])
end
return value
"""
    _CONFIRM_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return -1
end
if current ~= ARGV[1] then
  return 0
end
if redis.call('EXISTS', KEYS[2]) == 1 then
  return -2
end
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[4])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[4], 'XX')
return 1
"""
    _UPDATE_RECORD_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return -1
end
if current ~= ARGV[1] then
  return 0
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3], 'XX')
return 1
"""

    def __init__(
        self,
        *,
        redis_client=None,
        cipher: PaymentTokenCipher | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._redis_client = redis_client
        self._client_initialized = redis_client is not None
        self._cipher = cipher or PaymentTokenCipher(
            settings.payment_token_encryption_key.get_secret_value()
        )
        self._ttl_seconds = int(ttl_seconds or settings.checkout_session_ttl_seconds)
        if self._ttl_seconds <= 0:
            raise CheckoutStoreError("Checkout session TTL must be positive")

    @staticmethod
    def request_fingerprint(subject: Mapping[str, Any]) -> str:
        try:
            canonical = json.dumps(
                dict(subject),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        except (TypeError, ValueError) as exc:
            raise CheckoutStoreError("Checkout request must be JSON serializable") from exc
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _client(self):
        if not self._client_initialized:
            settings = get_settings()
            try:
                self._redis_client = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                )
            except (RedisError, OSError, ValueError, TypeError) as exc:
                raise CheckoutStoreUnavailable("Checkout Redis is unavailable") from exc
            self._client_initialized = True
        return self._redis_client

    @classmethod
    def _session_key(cls, opaque_id: str) -> str:
        return f"{cls.SESSION_PREFIX}:{opaque_id}"

    @classmethod
    def _token_key(cls, opaque_id: str) -> str:
        return f"{cls.TOKEN_PREFIX}:{opaque_id}"

    @classmethod
    def _idempotency_key(cls, app_user_id: str, idempotency_key: str) -> str:
        if not idempotency_key:
            raise CheckoutStoreError("Idempotency key is required")
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"{cls.IDEMPOTENCY_PREFIX}:{app_user_id}:{digest}"

    def _remaining_ttl(self, record: CheckoutSessionRecord) -> int:
        remaining = math.ceil(
            (record.expires_at - datetime.now(timezone.utc)).total_seconds()
        )
        if remaining <= 0:
            raise CheckoutSessionNotFound("Checkout session expired")
        return min(self._ttl_seconds, remaining)

    def save(
        self,
        record: CheckoutSessionRecord,
        *,
        idempotency_key: str,
    ) -> CheckoutSaveResult:
        ttl = self._remaining_ttl(record)
        state_json = json.dumps(
            record.to_dict(), separators=(",", ":"), sort_keys=True
        )
        ciphertext = self._cipher.encrypt(state_json)
        index_value = f"{record.request_fingerprint}:{record.opaque_id}"
        try:
            result = self._client().eval(
                self._SAVE_SCRIPT,
                2,
                self._session_key(record.opaque_id),
                self._idempotency_key(record.app_user_id, idempotency_key),
                ciphertext,
                ttl,
                index_value,
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to persist checkout session") from exc
        try:
            reused = bool(int(result[0]))
            existing_fingerprint, existing_id = str(result[1]).split(":", 1)
        except (TypeError, ValueError, IndexError) as exc:
            raise CheckoutSessionCorrupt("Invalid checkout idempotency index") from exc
        if existing_fingerprint != record.request_fingerprint:
            raise CheckoutIdempotencyConflict("Idempotency key request conflict")
        if reused:
            return CheckoutSaveResult(record=self.get(existing_id), reused=True)
        return CheckoutSaveResult(record=record, reused=False)

    def get_by_idempotency(
        self,
        *,
        app_user_id: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> CheckoutSessionRecord | None:
        """Return an existing valid session before re-running mutable target checks."""
        try:
            index_value = self._client().get(
                self._idempotency_key(app_user_id, idempotency_key)
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to read checkout idempotency state") from exc
        if not index_value:
            return None
        try:
            existing_fingerprint, existing_id = str(index_value).split(":", 1)
        except (TypeError, ValueError) as exc:
            raise CheckoutSessionCorrupt("Invalid checkout idempotency index") from exc
        if existing_fingerprint != request_fingerprint:
            raise CheckoutIdempotencyConflict("Idempotency key request conflict")
        try:
            return self.get(existing_id)
        except CheckoutSessionNotFound as exc:
            raise CheckoutSessionCorrupt(
                "Checkout idempotency state points to a missing session"
            ) from exc

    def get(self, opaque_id: str) -> CheckoutSessionRecord:
        try:
            ciphertext = self._client().get(self._session_key(opaque_id))
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to read checkout session") from exc
        if not ciphertext:
            raise CheckoutSessionNotFound("Checkout session not found")
        return self._decode_record(opaque_id, ciphertext)

    def _decode_record(
        self, opaque_id: str, ciphertext: str | bytes
    ) -> CheckoutSessionRecord:
        try:
            payload = json.loads(self._cipher.decrypt(ciphertext))
            record = CheckoutSessionRecord.from_dict(payload)
        except (PaymentTokenCryptoError, CheckoutSessionStateError, json.JSONDecodeError) as exc:
            raise CheckoutSessionCorrupt("Checkout session state is invalid") from exc
        if record.opaque_id != opaque_id:
            raise CheckoutSessionCorrupt("Checkout session identity mismatch")
        if record.expires_at <= datetime.now(timezone.utc):
            self.delete(opaque_id)
            raise CheckoutSessionNotFound("Checkout session expired")
        return record

    def transition(
        self,
        opaque_id: str,
        target: CheckoutSessionStatus,
    ) -> CheckoutSessionRecord:
        key = self._session_key(opaque_id)
        try:
            current_ciphertext = self._client().get(key)
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to read checkout session") from exc
        if not current_ciphertext:
            raise CheckoutSessionNotFound("Checkout session not found")
        record = self._decode_record(opaque_id, current_ciphertext).transition_to(target)
        ttl = self._remaining_ttl(record)
        next_ciphertext = self._cipher.encrypt(
            json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
        )
        try:
            written = int(
                self._client().eval(
                    self._TRANSITION_SCRIPT,
                    1,
                    key,
                    current_ciphertext,
                    next_ciphertext,
                    ttl,
                )
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to update checkout session") from exc
        if written == -1:
            raise CheckoutSessionNotFound("Checkout session not found")
        if written != 1:
            raise CheckoutTransitionConflict("Checkout session changed concurrently")
        return record

    def store_card_token(self, opaque_id: str, card_token: str) -> None:
        record = self.get(opaque_id)
        ttl = self._remaining_ttl(record)
        ciphertext = self._cipher.encrypt(card_token)
        try:
            stored = self._client().set(
                self._token_key(opaque_id), ciphertext, ex=ttl, nx=True
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to persist payment token") from exc
        if not stored:
            raise CheckoutTokenAlreadyStored("Payment token already stored")

    def confirm(
        self,
        opaque_id: str,
        *,
        card_token: str,
        confirmation: Mapping[str, Any],
    ) -> CheckoutSessionRecord:
        """Atomically persist the encrypted token and advance CREATED to READY."""
        session_key = self._session_key(opaque_id)
        token_key = self._token_key(opaque_id)
        try:
            current_ciphertext = self._client().get(session_key)
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to read checkout session") from exc
        if not current_ciphertext:
            raise CheckoutSessionNotFound("Checkout session not found")

        current = self._decode_record(opaque_id, current_ciphertext)
        if current.status is not CheckoutSessionStatus.CREATED:
            raise CheckoutTransitionConflict("Checkout session is not confirmable")
        next_data = dict(current.data)
        next_data["confirmation"] = dict(confirmation)
        next_record = replace(current, data=next_data).transition_to(
            CheckoutSessionStatus.READY
        )
        ttl = self._remaining_ttl(next_record)
        next_ciphertext = self._cipher.encrypt(
            json.dumps(next_record.to_dict(), separators=(",", ":"), sort_keys=True)
        )
        token_ciphertext = self._cipher.encrypt(card_token)
        try:
            written = int(
                self._client().eval(
                    self._CONFIRM_SCRIPT,
                    2,
                    session_key,
                    token_key,
                    current_ciphertext,
                    next_ciphertext,
                    token_ciphertext,
                    ttl,
                )
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to confirm checkout session") from exc
        if written == -1:
            raise CheckoutSessionNotFound("Checkout session not found")
        if written == -2:
            raise CheckoutTokenAlreadyStored("Payment token already stored")
        if written != 1:
            raise CheckoutTransitionConflict("Checkout session changed concurrently")
        return next_record

    def consume_card_token(self, opaque_id: str) -> str:
        client = self._client()
        try:
            getdel = getattr(client, "getdel", None)
            if callable(getdel):
                ciphertext = getdel(self._token_key(opaque_id))
            else:
                ciphertext = client.eval(
                    self._GET_DELETE_SCRIPT, 1, self._token_key(opaque_id)
                )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to consume payment token") from exc
        if not ciphertext:
            raise CheckoutTokenUnavailable("Payment token is unavailable")
        try:
            return self._cipher.decrypt(ciphertext)
        except PaymentTokenCryptoError as exc:
            raise CheckoutTokenUnavailable("Payment token is unavailable") from exc

    def update_record(
        self,
        opaque_id: str,
        *,
        status: CheckoutSessionStatus,
        results: Mapping[str, Any],
    ) -> CheckoutSessionRecord:
        """Atomically publish a safe provider result after a card operation."""
        key = self._session_key(opaque_id)
        try:
            current_ciphertext = self._client().get(key)
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to read checkout session") from exc
        if not current_ciphertext:
            raise CheckoutSessionNotFound("Checkout session not found")
        current = self._decode_record(opaque_id, current_ciphertext)
        next_data = dict(current.data)
        next_data["results"] = dict(results)
        next_record = replace(current, data=next_data).transition_to(status)
        ttl = self._remaining_ttl(next_record)
        next_ciphertext = self._cipher.encrypt(
            json.dumps(next_record.to_dict(), separators=(",", ":"), sort_keys=True)
        )
        try:
            written = int(
                self._client().eval(
                    self._UPDATE_RECORD_SCRIPT,
                    1,
                    key,
                    current_ciphertext,
                    next_ciphertext,
                    ttl,
                )
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to update checkout session") from exc
        if written == -1:
            raise CheckoutSessionNotFound("Checkout session not found")
        if written != 1:
            raise CheckoutTransitionConflict("Checkout session changed concurrently")
        return next_record

    def delete(self, opaque_id: str) -> None:
        try:
            self._client().delete(
                self._session_key(opaque_id), self._token_key(opaque_id)
            )
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise CheckoutStoreUnavailable("Unable to delete checkout session") from exc
