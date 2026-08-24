"""Short-lived checkout session storage primitives."""

from app.services.payment_checkout.crypto import PaymentTokenCipher
from app.services.payment_checkout.models import (
    CheckoutSessionRecord,
    CheckoutSessionStatus,
)
from app.services.payment_checkout.redis_store import CheckoutSessionStore
from app.services.payment_checkout.signing import CheckoutURLSigner


def __getattr__(name):
    """Load the service layer lazily to avoid a reconciliation import cycle."""
    if name in {
        "ConfirmCheckoutSessionCommand",
        "CheckoutSessionService",
        "CreateCheckoutSessionCommand",
        "HostedCheckoutPage",
        "PaymentMethodMode",
    }:
        from app.services.payment_checkout import service

        return getattr(service, name)
    raise AttributeError(name)

__all__ = [
    "CheckoutSessionRecord",
    "CheckoutSessionStatus",
    "CheckoutSessionStore",
    "CheckoutSessionService",
    "CheckoutURLSigner",
    "ConfirmCheckoutSessionCommand",
    "CreateCheckoutSessionCommand",
    "HostedCheckoutPage",
    "PaymentMethodMode",
    "PaymentTokenCipher",
]
