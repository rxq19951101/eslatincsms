import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from app.database.models import AppUser, AppWalletTransaction, PaymentOrder, Tenant
from app.domain.payment import transition_status
from app.api.v1.app.payments import _apply_approved_business_logic


def test_payment_state_machine_rejects_rollback():
    assert transition_status("created", "processing") == "processing"
    assert transition_status("approved", "refunded") == "refunded"
    with pytest.raises(ValueError):
        transition_status("approved", "declined")


def test_approved_topup_is_ledger_idempotent(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="payment-tenant", status="active")
    user = AppUser(
        id=uuid.uuid4(), email="phase4@example.com", password_hash="test", balance=Decimal("0")
    )
    order = PaymentOrder(
        id=uuid.uuid4(), app_user_id=user.id, type="top_up", amount=Decimal("100.00"),
        currency="COP", payment_provider="wompi", status="approved",
        reference="PHASE4-REF", expires_at=datetime.now(timezone.utc),
    )
    db_session.add_all([tenant, user, order])
    db_session.flush()

    _apply_approved_business_logic(db_session, order, user, "test", "phase4")
    db_session.commit()
    _apply_approved_business_logic(db_session, order, user, "test", "phase4")
    db_session.commit()

    db_session.refresh(user)
    assert user.balance == Decimal("100.00")
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.payment_order_id == order.id,
        AppWalletTransaction.type == "top_up",
    ).count() == 1
