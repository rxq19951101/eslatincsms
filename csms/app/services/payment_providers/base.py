from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol


@dataclass
class CreatePaymentCommand:
    provider: str
    order_type: str
    amount: Decimal
    currency: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    email: Optional[str] = None
    token: Optional[str] = None
    payment_method_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    device_id: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ProviderCreateResult:
    status: str
    provider_order_ref: Optional[str] = None
    provider_payment_id: Optional[str] = None
    redirect_url: Optional[str] = None
    checkout_payload: Optional[Dict[str, Any]] = None
    raw_response: Optional[Dict[str, Any]] = None


class PaymentProvider(Protocol):
    provider_code: str

    def create_payment(self, command: CreatePaymentCommand) -> ProviderCreateResult:
        ...

