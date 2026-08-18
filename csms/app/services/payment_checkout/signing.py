"""Short-lived, tamper-evident checkout URL tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


class CheckoutSigningError(RuntimeError):
    """Safe signing failure that never includes key or token material."""


@dataclass(frozen=True)
class CheckoutSignedToken:
    opaque_id: str
    expires_at: datetime
    nonce: str


_OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CheckoutSigningError("Invalid checkout URL signature") from exc


class CheckoutURLSigner:
    """HMAC signer whose payload contains only session id, expiry, and nonce."""

    VERSION = "v1"

    def __init__(
        self,
        signing_key: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(signing_key, str) or len(signing_key.strip()) < 32:
            raise CheckoutSigningError(
                "Checkout signing key must contain at least 32 characters"
            )
        self._key = signing_key.strip().encode("utf-8")
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def sign(self, *, opaque_id: str, expires_at: datetime, nonce: str) -> str:
        if not _OPAQUE_VALUE.fullmatch(opaque_id):
            raise CheckoutSigningError("Invalid checkout session id")
        if not _OPAQUE_VALUE.fullmatch(nonce):
            raise CheckoutSigningError("Invalid checkout signing nonce")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise CheckoutSigningError("Checkout expiry must be timezone-aware")
        expires_at = expires_at.astimezone(timezone.utc)
        if expires_at <= self._now():
            raise CheckoutSigningError("Checkout URL has expired")

        payload = json.dumps(
            {
                "exp": int(expires_at.timestamp()),
                "nonce": nonce,
                "sid": opaque_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded_payload = _encode(payload)
        signing_input = f"{self.VERSION}.{encoded_payload}".encode("ascii")
        signature = _encode(hmac.new(self._key, signing_input, hashlib.sha256).digest())
        return f"{self.VERSION}.{encoded_payload}.{signature}"

    def verify(self, token: str) -> CheckoutSignedToken:
        if not isinstance(token, str) or len(token) > 2048:
            raise CheckoutSigningError("Invalid checkout URL signature")
        try:
            version, encoded_payload, encoded_signature = token.split(".")
        except ValueError as exc:
            raise CheckoutSigningError("Invalid checkout URL signature") from exc
        if version != self.VERSION:
            raise CheckoutSigningError("Invalid checkout URL signature")

        signing_input = f"{version}.{encoded_payload}".encode("ascii")
        expected = _encode(hmac.new(self._key, signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, encoded_signature):
            raise CheckoutSigningError("Invalid checkout URL signature")

        try:
            payload = json.loads(_decode(encoded_payload))
            opaque_id = str(payload["sid"])
            nonce = str(payload["nonce"])
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CheckoutSigningError("Invalid checkout URL signature") from exc
        if set(payload) != {"exp", "nonce", "sid"}:
            raise CheckoutSigningError("Invalid checkout URL signature")
        if not _OPAQUE_VALUE.fullmatch(opaque_id) or not _OPAQUE_VALUE.fullmatch(nonce):
            raise CheckoutSigningError("Invalid checkout URL signature")
        if expires_at <= self._now():
            raise CheckoutSigningError("Checkout URL has expired")
        return CheckoutSignedToken(
            opaque_id=opaque_id,
            expires_at=expires_at,
            nonce=nonce,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise CheckoutSigningError("Checkout signing clock must be timezone-aware")
        return value.astimezone(timezone.utc)
