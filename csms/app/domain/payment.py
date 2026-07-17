from enum import Enum


class PaymentOrderStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    APPROVED = "approved"
    DECLINED = "declined"
    VOIDED = "voided"
    ERROR = "error"
    EXPIRED = "expired"
    REFUNDED = "refunded"


_TRANSITIONS = {
    PaymentOrderStatus.CREATED: {
        PaymentOrderStatus.CREATED,
        PaymentOrderStatus.PROCESSING,
        PaymentOrderStatus.APPROVED,
        PaymentOrderStatus.DECLINED,
        PaymentOrderStatus.VOIDED,
        PaymentOrderStatus.ERROR,
        PaymentOrderStatus.EXPIRED,
    },
    PaymentOrderStatus.PROCESSING: {
        PaymentOrderStatus.PROCESSING,
        PaymentOrderStatus.APPROVED,
        PaymentOrderStatus.DECLINED,
        PaymentOrderStatus.VOIDED,
        PaymentOrderStatus.ERROR,
        PaymentOrderStatus.EXPIRED,
    },
    PaymentOrderStatus.APPROVED: {PaymentOrderStatus.APPROVED, PaymentOrderStatus.REFUNDED},
    PaymentOrderStatus.DECLINED: {PaymentOrderStatus.DECLINED},
    PaymentOrderStatus.VOIDED: {PaymentOrderStatus.VOIDED},
    PaymentOrderStatus.ERROR: {PaymentOrderStatus.ERROR},
    PaymentOrderStatus.EXPIRED: {PaymentOrderStatus.EXPIRED},
    PaymentOrderStatus.REFUNDED: {PaymentOrderStatus.REFUNDED},
}


def transition_status(current: str, target: str) -> str:
    current_status = PaymentOrderStatus(current)
    target_status = PaymentOrderStatus(target)
    if target_status not in _TRANSITIONS[current_status]:
        raise ValueError(f"Invalid payment status transition: {current} -> {target}")
    return target_status.value
