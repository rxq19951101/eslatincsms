from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.database.models import (
    AppUser,
    AppWalletTransaction,
    ChargingSession,
    Invoice,
    Order,
    Payment,
    PaymentOrder,
    PricingSnapshot,
    Tariff,
)
from app.services.billing_service import BillingService
from app.services.pricing_service import PricingMode, PricingService


def _settlement_fixture(
    db,
    sample_tenant,
    sample_charge_point,
    sample_evse,
    *,
    settlement_method="wallet",
    balance="10000.00",
    price="2700.00",
    pricing_mode=PricingMode.PAID,
    meter_stop=1000,
):
    now = datetime.now(timezone.utc)
    user = AppUser(
        email=f"be5-{settlement_method}-{price}-{balance}@example.test",
        password_hash="test",
        balance=Decimal(balance),
    )
    db.add(user)
    db.flush()
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=900000 + db.query(ChargingSession).count(),
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=now - timedelta(minutes=10),
        end_time=now,
        meter_start=0,
        meter_stop=meter_stop,
        status="completed",
        payment_status="unpaid",
    )
    order = Order(
        tenant_id=sample_tenant.id,
        session_id=session.id,
        charge_point_id=sample_charge_point.id,
        user_id=str(user.id),
        app_user_id=user.id,
        id_tag=session.id_tag,
        status="completed",
        pre_authorization={"settlement_method": settlement_method},
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_charge_point.site_id,
        charge_point_id=sample_charge_point.id,
        name="BE-5 tariff",
        base_price_per_kwh=Decimal(price),
        service_fee=Decimal("0.00"),
        time_based_rules=PricingService.metadata(pricing_mode),
        valid_from=now - timedelta(days=1),
        is_active=True,
    )
    db.add(session)
    db.flush()
    order.session_id = session.id
    db.add_all([order, tariff])
    db.flush()
    snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        order_id=order.id,
        price_per_kwh=(
            Decimal("0.00") if pricing_mode == PricingMode.FREE else Decimal(price)
        ),
        service_fee=Decimal("0.00"),
        snapshot_data=PricingService.metadata(pricing_mode),
        snapshot_time=session.start_time,
    )
    db.add(snapshot)
    db.commit()
    return user, session


def test_wallet_insufficient_funds_remains_unpaid_without_truncation(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        balance="100.00",
        meter_stop=1000,
    )

    first = BillingService.settle_session(db_session, session, user)
    second = BillingService.settle_session(db_session, session, user)

    assert first.payment_status == "unpaid"
    assert first.already_settled is False
    assert first.balance == Decimal("100.00")
    assert second.invoice_id == first.invoice_id
    assert db_session.query(Invoice).filter(Invoice.session_id == session.id).count() == 1
    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    assert invoice.status == "pending"
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 0
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.invoice_id == invoice.id
    ).count() == 0
    assert db_session.get(AppUser, user.id).balance == Decimal("100.00")
    assert db_session.get(ChargingSession, session.id).payment_status == "unpaid"


def test_paid_charging_invoice_uses_minimum_amount_for_small_consumption(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        settlement_method="direct_card",
        balance="0.00",
        price="100.00",
        meter_stop=1,
    )

    result = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    payment_order = db_session.query(PaymentOrder).filter(
        PaymentOrder.id == session.payment_order_id
    ).one()
    assert result.payment_status == "processing"
    assert invoice.total_amount == Decimal("1011.00")
    assert payment_order.amount == Decimal("1011.00")


def test_paid_minimum_matches_provider_verified_boundary():
    assert BillingService._minimum_paid_total(Decimal("1010.00")) == Decimal("1011.00")
    assert BillingService._minimum_paid_total(Decimal("1011.00")) == Decimal("1011.00")
    assert BillingService._minimum_paid_total(Decimal("1012.00")) == Decimal("1012.00")
    assert BillingService._minimum_paid_total(
        Decimal("1.00"), pricing_mode="free"
    ) == Decimal("1.00")


def test_free_charging_does_not_inherit_paid_minimum(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        settlement_method="wallet",
        balance="100.00",
        price="100.00",
        pricing_mode=PricingMode.FREE,
        meter_stop=1,
    )

    result = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    assert result.charged_amount == Decimal("0.00")
    assert invoice.total_amount == Decimal("0.00")


def test_wallet_exact_balance_has_one_full_payment_and_one_ledger(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        balance="2700.00",
        meter_stop=1000,
    )

    result = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    assert result.payment_status == "paid"
    assert invoice.total_amount == Decimal("2700.00")
    assert invoice.status == "paid"
    assert db_session.get(AppUser, user.id).balance == Decimal("0.00")
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.invoice_id == invoice.id
    ).count() == 1


def test_direct_card_creates_one_exact_payment_order_without_wallet_mutation(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        settlement_method="direct_card",
        balance="0.00",
        meter_stop=1000,
    )

    first = BillingService.settle_session(db_session, session, user)
    second = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    payment_orders = db_session.query(PaymentOrder).filter(
        PaymentOrder.app_user_id == user.id
    ).all()
    assert first.payment_status == "processing"
    assert second.payment_order_id == first.payment_order_id
    assert len(payment_orders) == 1
    assert payment_orders[0].amount == invoice.total_amount == Decimal("2700.00")
    assert payment_orders[0].status == "created"
    assert invoice.status == "pending"
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 0
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.app_user_id == user.id
    ).count() == 0
    assert db_session.get(AppUser, user.id).balance == Decimal("0.00")


def test_direct_card_approved_order_completes_invoice_without_wallet(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        settlement_method="direct_card",
        balance="0.00",
        meter_stop=1000,
    )
    pending = BillingService.settle_session(db_session, session, user)
    payment_order = db_session.get(PaymentOrder, UUID(pending.payment_order_id))
    payment_order.status = "approved"
    payment_order.mercadopago_payment_id = "mp-be5-approved-1"
    db_session.commit()

    result = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    assert result.payment_status == "paid"
    assert result.balance is None
    assert invoice.status == "paid"
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.app_user_id == user.id
    ).count() == 0


def test_free_zero_cop_creates_audit_payment_only_and_is_idempotent(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session = _settlement_fixture(
        db_session,
        sample_tenant,
        sample_charge_point,
        sample_evse,
        settlement_method="wallet",
        balance="10.00",
        price="0.00",
        pricing_mode=PricingMode.FREE,
        meter_stop=50000,
    )

    first = BillingService.settle_session(db_session, session, user)
    second = BillingService.settle_session(db_session, session, user)

    invoice = db_session.query(Invoice).filter(Invoice.session_id == session.id).one()
    assert first.payment_status == "paid"
    assert second.already_settled is True
    assert invoice.total_amount == Decimal("0.00")
    assert invoice.status == "paid"
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice.id).count() == 1
    assert db_session.query(PaymentOrder).filter(
        PaymentOrder.app_user_id == user.id
    ).count() == 0
    assert db_session.query(AppWalletTransaction).filter(
        AppWalletTransaction.app_user_id == user.id
    ).count() == 0
    assert db_session.get(AppUser, user.id).balance == Decimal("10.00")
