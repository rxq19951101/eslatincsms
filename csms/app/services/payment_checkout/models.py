"""Versioned, non-sensitive checkout session state."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import UUID

from app.services.payment_providers.merchant_context import PaymentPurpose


class CheckoutSessionStateError(ValueError):
    """Raised when checkout state is invalid or contains secret material."""


class CheckoutSessionStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    PROCESSING = "processing"
    ACTION_REQUIRED = "action_required"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    ERROR = "error"


_TRANSITIONS = {
    CheckoutSessionStatus.CREATED: {
        CheckoutSessionStatus.CREATED,
        CheckoutSessionStatus.READY,
        CheckoutSessionStatus.EXPIRED,
        CheckoutSessionStatus.ERROR,
    },
    CheckoutSessionStatus.READY: {
        CheckoutSessionStatus.READY,
        CheckoutSessionStatus.PROCESSING,
        CheckoutSessionStatus.APPROVED,
        CheckoutSessionStatus.EXPIRED,
        CheckoutSessionStatus.ERROR,
    },
    CheckoutSessionStatus.PROCESSING: {
        CheckoutSessionStatus.PROCESSING,
        CheckoutSessionStatus.ACTION_REQUIRED,
        CheckoutSessionStatus.APPROVED,
        CheckoutSessionStatus.DECLINED,
        CheckoutSessionStatus.EXPIRED,
        CheckoutSessionStatus.ERROR,
    },
    CheckoutSessionStatus.ACTION_REQUIRED: {
        CheckoutSessionStatus.ACTION_REQUIRED,
        CheckoutSessionStatus.PROCESSING,
        CheckoutSessionStatus.APPROVED,
        CheckoutSessionStatus.DECLINED,
        CheckoutSessionStatus.EXPIRED,
        CheckoutSessionStatus.ERROR,
    },
    CheckoutSessionStatus.APPROVED: {CheckoutSessionStatus.APPROVED},
    CheckoutSessionStatus.DECLINED: {CheckoutSessionStatus.DECLINED},
    CheckoutSessionStatus.EXPIRED: {CheckoutSessionStatus.EXPIRED},
    CheckoutSessionStatus.ERROR: {CheckoutSessionStatus.ERROR},
}

_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
_SENSITIVE_KEY_PARTS = (
    "token",
    "password",
    "secret",
    "credential",
    "authorization",
    "card_number",
    "security_code",
)
_SENSITIVE_EXACT_KEYS = {"pan", "cvv", "cvc"}


def _assert_no_sensitive_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in _SENSITIVE_EXACT_KEYS or any(
                part in normalized for part in _SENSITIVE_KEY_PARTS
            ):
                raise CheckoutSessionStateError(
                    "Sensitive fields are forbidden in checkout session state"
                )
            _assert_no_sensitive_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_sensitive_fields(item)


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CheckoutSessionStateError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class CheckoutSessionRecord:
    opaque_id: str
    app_user_id: str
    purpose: PaymentPurpose
    status: CheckoutSessionStatus
    request_fingerprint: str
    created_at: datetime
    expires_at: datetime
    data: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise CheckoutSessionStateError("Unsupported checkout state version")
        if not _OPAQUE_ID.fullmatch(self.opaque_id):
            raise CheckoutSessionStateError("Invalid checkout session id")
        try:
            normalized_user_id = str(UUID(str(self.app_user_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise CheckoutSessionStateError("Invalid app user id") from exc
        if not _FINGERPRINT.fullmatch(self.request_fingerprint):
            raise CheckoutSessionStateError("Invalid request fingerprint")
        created_at = _utc(self.created_at, "created_at")
        expires_at = _utc(self.expires_at, "expires_at")
        if expires_at <= created_at:
            raise CheckoutSessionStateError("Checkout session must expire after creation")
        _assert_no_sensitive_fields(self.data)
        try:
            safe_data = json.loads(
                json.dumps(dict(self.data), separators=(",", ":"), sort_keys=True)
            )
        except (TypeError, ValueError) as exc:
            raise CheckoutSessionStateError("Checkout state must be JSON serializable") from exc
        object.__setattr__(self, "app_user_id", normalized_user_id)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "data", safe_data)

    def transition_to(self, target: CheckoutSessionStatus) -> "CheckoutSessionRecord":
        target = CheckoutSessionStatus(target)
        if target not in _TRANSITIONS[self.status]:
            raise CheckoutSessionStateError(
                f"Invalid checkout state transition: {self.status.value} -> {target.value}"
            )
        return replace(self, status=target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opaque_id": self.opaque_id,
            "app_user_id": self.app_user_id,
            "purpose": self.purpose.value,
            "status": self.status.value,
            "request_fingerprint": self.request_fingerprint,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CheckoutSessionRecord":
        try:
            return cls(
                schema_version=int(value["schema_version"]),
                opaque_id=str(value["opaque_id"]),
                app_user_id=str(value["app_user_id"]),
                purpose=PaymentPurpose(str(value["purpose"])),
                status=CheckoutSessionStatus(str(value["status"])),
                request_fingerprint=str(value["request_fingerprint"]),
                created_at=datetime.fromisoformat(str(value["created_at"])),
                expires_at=datetime.fromisoformat(str(value["expires_at"])),
                data=value.get("data") or {},
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, CheckoutSessionStateError):
                raise
            raise CheckoutSessionStateError("Invalid checkout session payload") from exc
