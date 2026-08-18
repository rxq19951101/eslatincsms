"""Server-trusted merchant selection for payment-provider calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional, Protocol
from uuid import UUID


class PaymentPurpose(str, Enum):
    SAVE_CARD = "save_card"
    WALLET_TOP_UP = "wallet_top_up"
    CHARGING_DIRECT = "charging_direct"
    UNPAID_CHARGE = "unpaid_charge"
    REFUND = "refund"
    RECONCILIATION = "reconciliation"


class MerchantMode(str, Enum):
    PLATFORM = "platform"
    MARKETPLACE = "marketplace"


class MerchantContextError(ValueError):
    """Raised when a trusted merchant context cannot be resolved."""


@dataclass(frozen=True)
class MerchantContext:
    merchant_mode: MerchantMode
    merchant_account_ref: str
    provider: str
    credential_handle: str = field(repr=False)
    marketplace_fee_policy: Optional[Mapping[str, str]] = None

    def __post_init__(self) -> None:
        if not self.merchant_account_ref or not self.provider or not self.credential_handle:
            raise MerchantContextError("Incomplete merchant context")
        if self.marketplace_fee_policy is not None:
            object.__setattr__(
                self,
                "marketplace_fee_policy",
                MappingProxyType(dict(self.marketplace_fee_policy)),
            )

    def safe_snapshot(self) -> dict[str, object]:
        """Return the only merchant fields allowed in persistence and logs."""
        return {
            "merchant_mode": self.merchant_mode.value,
            "merchant_account_ref": self.merchant_account_ref,
            "provider": self.provider,
            "marketplace_fee_policy": (
                dict(self.marketplace_fee_policy)
                if self.marketplace_fee_policy is not None
                else None
            ),
        }


class MerchantAccountResolver(Protocol):
    def resolve(
        self,
        *,
        operator_tenant_id: UUID | None,
        payment_purpose: PaymentPurpose,
    ) -> MerchantContext:
        ...


class PlatformMerchantAccountResolver:
    """C1 policy: EsLatin is the merchant of record for every payment."""

    _TENANT_REQUIRED_PURPOSES = frozenset(
        {
            PaymentPurpose.CHARGING_DIRECT,
            PaymentPurpose.UNPAID_CHARGE,
            PaymentPurpose.REFUND,
            PaymentPurpose.RECONCILIATION,
        }
    )

    def __init__(
        self,
        *,
        provider: str = "mercadopago",
        merchant_account_ref: str = "platform:eslatin",
        credential_handle: str = "env:mercadopago:platform",
    ) -> None:
        self._provider = provider
        self._merchant_account_ref = merchant_account_ref
        self._credential_handle = credential_handle

    def resolve(
        self,
        *,
        operator_tenant_id: UUID | None,
        payment_purpose: PaymentPurpose,
    ) -> MerchantContext:
        if (
            payment_purpose in self._TENANT_REQUIRED_PURPOSES
            and operator_tenant_id is None
        ):
            raise MerchantContextError(
                "A trusted operator tenant is required for this payment purpose"
            )
        return MerchantContext(
            merchant_mode=MerchantMode.PLATFORM,
            merchant_account_ref=self._merchant_account_ref,
            provider=self._provider,
            credential_handle=self._credential_handle,
            marketplace_fee_policy=None,
        )

    def resolve_legacy_platform_context(self) -> MerchantContext:
        """Temporary C1 bridge for routes that predate trusted merchant input.

        New charging, refund, webhook, and reconciliation flows must call
        ``resolve`` with a server-derived tenant. This bridge is removed in BE-6.
        """
        return MerchantContext(
            merchant_mode=MerchantMode.PLATFORM,
            merchant_account_ref=self._merchant_account_ref,
            provider=self._provider,
            credential_handle=self._credential_handle,
            marketplace_fee_policy=None,
        )
