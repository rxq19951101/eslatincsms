from __future__ import annotations

import re
from typing import Any, Mapping


REDACTED = "[REDACTED]"
SENSITIVE_KEY_RE = re.compile(
    r"(^|[_-])(password|secret|token|authorization|api[_-]?key|card[_-]?number|cvv|security[_-]?code|signature)($|[_-])",
    re.IGNORECASE,
)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
QUERY_SECRET_RE = re.compile(
    r"(?i)(password|secret|token|authorization|api_key|signature)=([^&\s]+)"
)
QR_PAYLOAD_RE = re.compile(r"(?i)\bqr:[A-Za-z0-9._~+/-]{8,}=*")


def redact(value: Any, key: str = "") -> Any:
    if key and SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = BEARER_RE.sub(f"Bearer {REDACTED}", value)
        result = JWT_RE.sub(REDACTED, result)
        result = CARD_RE.sub(REDACTED, result)
        result = QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", result)
        result = QR_PAYLOAD_RE.sub(f"qr:{REDACTED}", result)
        return result
    return value
