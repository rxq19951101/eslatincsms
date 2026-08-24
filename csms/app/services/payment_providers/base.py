from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Literal, Mapping, Optional, Protocol

from app.services.payment_providers.merchant_context import MerchantContext


ProviderPaymentType = Literal["credit_card", "debit_card", "prepaid_card"]

# These values are the only payment facts the orchestration layer is allowed
# to understand.  Provider adapters may accept a much larger set of SDK
# states, but they must normalize them before crossing this boundary.
CanonicalPaymentStatus = Literal[
    "processing",
    "action_required",
    "provider_approved",
    "declined",
    "unknown",
    "refunded",
    "disputed",
    "mismatch",
]


@dataclass(frozen=True)
class ProviderNextAction:
    """A safe, provider-neutral action projection."""

    type: Literal["open_url", "poll", "none"]
    url: Optional[str] = None


@dataclass(frozen=True)
class PaymentCapabilityCommand:
    """Input accepted by a provider adapter.

    ``references`` is intentionally limited to non-sensitive application
    references.  It must never contain a raw SDK payload, PAN, CVV, access
    token, or a provider object.  A hosted/one-time instrument token is
    carried as an opaque value and is consumed only by the adapter.
    """

    amount: Decimal
    currency: str
    purpose: str
    merchant_account_ref: str
    references: Mapping[str, str] = field(default_factory=dict)
    instrument_token: Optional[str] = None
    payment_method_hint: Optional[str] = None
    payment_type_hint: Optional[str] = None


@dataclass(frozen=True)
class PaymentCapabilityResult:
    """Canonical result of payment creation or an authoritative query."""

    status: CanonicalPaymentStatus
    provider_ref: Optional[str] = None
    merchant_ref: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    next_action: Optional[ProviderNextAction] = None


@dataclass(frozen=True)
class RefundCapabilityCommand:
    payment_ref: str
    amount: Decimal
    currency: str
    merchant_account_ref: str
    references: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundCapabilityResult:
    status: Literal["processing", "refunded", "unknown", "mismatch"]
    refund_ref: Optional[str] = None
    amount: Optional[Decimal] = None


@dataclass(frozen=True)
class RefundCapabilityFacts:
    refunded_amount: Decimal
    refund_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DisputeCapabilityFact:
    payment_ref: str
    status: Literal["disputed", "unknown", "reversed"]
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    dispute_ref: Optional[str] = None
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class FundsCapabilityFact:
    payment_ref: str
    status: Literal["released", "held", "unknown", "mismatch"]
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    funds_ref: Optional[str] = None


class ProviderCapabilityError(RuntimeError):
    """Canonical provider failure; adapter details never cross this type."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        self.reason = reason
        self.retryable = retryable
        super().__init__(reason)


class PaymentProviderError(RuntimeError):
    """Provider failure safe to surface to application logs and handlers."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


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
    next_action_url: Optional[str] = None
    checkout_payload: Optional[Dict[str, Any]] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ProviderPaymentStatus:
    """Safe provider facts used by the shared reconciliation service."""

    status: str
    provider_payment_id: Optional[str]
    external_reference: Optional[str]
    amount: Decimal
    currency: str
    next_action_url: Optional[str] = None


@dataclass(frozen=True)
class ProviderRefundFacts:
    """Provider-authoritative cumulative refund facts."""

    refunded_amount: Decimal
    refund_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderRefundResult:
    """Safe result for a newly requested refund."""

    refund_id: Optional[str]
    status: str
    amount: Decimal


@dataclass(frozen=True)
class ProviderCustomerResult:
    customer_id: str


@dataclass(frozen=True)
class ProviderCardResult:
    customer_id: str
    card_id: str
    brand: str
    payment_type: ProviderPaymentType
    last_four: str


class PaymentProvider(Protocol):
    provider_code: str

    def create_recovery_payment(
        self,
        command: PaymentCapabilityCommand,
        *,
        merchant_context: MerchantContext,
        idempotency_key: str,
    ) -> PaymentCapabilityResult:
        """Create a payment using only canonical application facts."""
        ...

    def query_payment(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> PaymentCapabilityResult:
        ...

    def create_refund_capability(
        self,
        command: RefundCapabilityCommand,
        *,
        merchant_context: MerchantContext,
        idempotency_key: str,
    ) -> RefundCapabilityResult:
        ...

    def query_refund_capability(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> RefundCapabilityFacts:
        ...

    # Stable capability names used by the P002 design.  The ``*_capability``
    # spellings above remain available for explicit legacy adapters.
    def query_refund_facts(
        self,
        provider_ref: str,
        *,
        merchant_context: MerchantContext,
    ) -> RefundCapabilityFacts:
        ...

    def normalize_dispute_fact(
        self,
        payload: Mapping[str, Any],
        *,
        merchant_context: MerchantContext,
    ) -> DisputeCapabilityFact:
        ...

    def normalize_funds_fact(
        self,
        payload: Mapping[str, Any],
        *,
        merchant_context: MerchantContext,
    ) -> FundsCapabilityFact:
        ...

    def ingest_dispute_fact(
        self,
        payload: Mapping[str, Any],
        *,
        merchant_context: MerchantContext,
    ) -> DisputeCapabilityFact:
        ...

    def ingest_funds_fact(
        self,
        payload: Mapping[str, Any],
        *,
        merchant_context: MerchantContext,
    ) -> FundsCapabilityFact:
        ...

    def create_payment(
        self,
        command: CreatePaymentCommand,
        *,
        merchant_context: Optional[MerchantContext] = None,
    ) -> ProviderCreateResult:
        ...

    def get_payment_status(
        self,
        payment_id: str,
        *,
        merchant_context: MerchantContext,
    ) -> ProviderPaymentStatus:
        ...

    def get_refund_facts(
        self,
        payment_id: str,
        *,
        merchant_context: MerchantContext,
    ) -> ProviderRefundFacts:
        ...

    def create_refund(
        self,
        payment_id: str,
        amount: Decimal,
        *,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> ProviderRefundResult:
        ...


class CustomerCardProvider(Protocol):
    provider_code: str

    def create_customer(
        self,
        *,
        email: str,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> ProviderCustomerResult:
        ...

    def create_card(
        self,
        *,
        customer_id: str,
        token: str,
        idempotency_key: str,
        payment_method_id: str | None,
        payment_type_id: str | None,
        merchant_context: MerchantContext,
    ) -> ProviderCardResult:
        ...

    def delete_card(
        self,
        *,
        customer_id: str,
        card_id: str,
        idempotency_key: str,
        merchant_context: MerchantContext,
    ) -> None:
        ...
