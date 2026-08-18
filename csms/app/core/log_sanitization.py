"""Log-safe recursive redaction utilities.

Redaction happens before a value is passed to ``logging``.  The logging filter
is defense in depth for call sites that do not use the helpers directly.
"""

from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "signature",
    "authorization",
    "credential",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "idempotency_key",
    "card_number",
    "security_code",
    "reset_url",
)
_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "card_token",
    "client_secret",
    "credential_handle",
    "key",
    "pwd",
    "pass",
    "pan",
    "cvv",
    "cvc",
    "qr",
    "qr_code",
    "qr_payload",
    "refresh_token",
    "x_signature",
    "x_sim_signature",
    "set_cookie",
}

_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?(?:qr[-_ ]?token|card[-_ ]?token|password|passwd|pwd|access[-_ ]?token|"
    r"refresh[-_ ]?token|webhook[-_ ]?(?:secret|signature)|secret|signature|"
    r"client[-_ ]?secret|credential[-_ ]?handle|authorization|api[-_ ]?key|"
    r"private[-_ ]?key)[\"']?\s*[:=]\s*)"
    r"([\"']?)[^\s&,;\"'}\]]+\2"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_PROVIDER_CREDENTIAL_RE = re.compile(
    r"\b(?:APP_USR|TEST)-[0-9]{6,}-[A-Za-z0-9_-]{16,}\b|"
    r"\b(?:prv|pub)_(?:test|prod)_[A-Za-z0-9]{16,}\b|"
    r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"
)
_CHECKOUT_SIGNED_PATH_RE = re.compile(
    r"(/api/v1/app/payments/checkout/)[^\s/?#]+"
)


def is_sensitive_log_key(key: Any) -> bool:
    """Return whether a mapping/header/extra key carries secret material."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
    return normalized in _SENSITIVE_EXACT_KEYS or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS
    )


def redact_log_text(value: str) -> str:
    """Remove embedded credentials from an otherwise useful log message."""
    safe = _BEARER_RE.sub("Bearer " + REDACTED, value)
    safe = _JWT_RE.sub(REDACTED, safe)
    safe = _PROVIDER_CREDENTIAL_RE.sub(REDACTED, safe)
    safe = _CHECKOUT_SIGNED_PATH_RE.sub(r"\1" + REDACTED, safe)
    safe = _ASSIGNMENT_RE.sub(lambda match: match.group(1) + REDACTED, safe)
    return safe


def redact_sensitive_data(value: Any, *, key: Any = None) -> Any:
    """Recursively copy ``value`` with all sensitive fields fully redacted."""
    if key is not None and is_sensitive_log_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        location = value.get("loc") or value.get("path")
        location_is_sensitive = isinstance(location, (list, tuple)) and any(
            is_sensitive_log_key(part) for part in location
        )
        return {
            item_key: (
                REDACTED
                if location_is_sensitive
                and str(item_key).lower() in {"input", "value", "given", "ctx"}
                else redact_sensitive_data(item_value, key=item_key)
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return sorted((redact_sensitive_data(item) for item in value), key=str)
    if isinstance(value, bytes):
        return redact_log_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, str):
        return redact_log_text(value)
    rendered = str(value)
    safe_rendered = redact_log_text(rendered)
    if safe_rendered != rendered:
        return safe_rendered
    return value


_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)


class SensitiveDataFilter(logging.Filter):
    """Defense-in-depth redaction of message, args, and custom LogRecord data."""

    def filter(self, record: logging.LogRecord) -> bool:
        message_has_sensitive_context = isinstance(record.msg, str) and any(
            marker in record.msg.lower()
            for marker in (
                "password",
                "token",
                "secret",
                "signature",
                "authorization",
                "credential",
                "reset url",
                "reset_url",
            )
        )
        record.msg = redact_sensitive_data(record.msg)
        if message_has_sensitive_context and record.args:
            if isinstance(record.args, Mapping):
                record.args = {
                    arg_key: REDACTED for arg_key in record.args
                }
            else:
                record.args = tuple(REDACTED for _ in record.args)
        else:
            record.args = redact_sensitive_data(record.args)
        if record.exc_info:
            record.exc_text = redact_log_text(
                "".join(traceback.format_exception(*record.exc_info))
            )
            record.exc_info = None
        for field in list(record.__dict__):
            if field not in _STANDARD_RECORD_FIELDS:
                record.__dict__[field] = redact_sensitive_data(
                    record.__dict__[field], key=field
                )
        return True
