"""Versioned compatibility codec for saved-card brand metadata.

The payment-method table predates ``payment_type``.  Keep the database shape
unchanged by storing the two safe provider labels in one versioned value.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


SUPPORTED_PAYMENT_TYPES = frozenset(
    {"credit_card", "debit_card", "prepaid_card"}
)
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class PaymentMethodDescriptor:
    brand: str | None
    payment_type: str | None


def _safe_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if _SAFE_LABEL.fullmatch(candidate) else None


def encode_payment_method_brand(
    brand: str,
    payment_type: str | None,
) -> str:
    """Encode provider card labels for the legacy brand column."""

    normalized_brand = _safe_label(brand)
    if not normalized_brand:
        raise ValueError("Payment method brand is invalid")
    normalized_type = _safe_label(payment_type) if payment_type else None
    if normalized_type not in SUPPORTED_PAYMENT_TYPES:
        raise ValueError("Payment method type is invalid")
    encoded = f"v1:{normalized_brand}:{normalized_type}"
    if len(encoded) > 64:
        raise ValueError("Payment method brand metadata is too long")
    return encoded


def decode_payment_method_brand(value: object) -> PaymentMethodDescriptor:
    """Decode current metadata and safely project legacy brand-only values."""

    if not isinstance(value, str):
        return PaymentMethodDescriptor(brand=None, payment_type=None)
    normalized = value.strip().lower()
    if not normalized:
        return PaymentMethodDescriptor(brand=None, payment_type=None)

    parts = normalized.split(":")
    if len(parts) == 3 and parts[0] == "v1":
        brand = _safe_label(parts[1])
        payment_type = parts[2] if parts[2] in SUPPORTED_PAYMENT_TYPES else None
        return PaymentMethodDescriptor(brand=brand, payment_type=payment_type)

    # Existing rows contain values such as ``visa`` or ``master``.
    return PaymentMethodDescriptor(brand=_safe_label(normalized), payment_type=None)
