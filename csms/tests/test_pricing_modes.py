from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.database.models import AppUser, AppWalletTransaction, Payment, PricingSnapshot, Tariff
from app.services.billing_service import BillingService
from app.services.pricing_service import PricingMode, PricingService
from app.services.session_service import SessionService


def _tariff(db, charge_point, *, price="2700.00", mode=None, source="site", valid_until=None):
    metadata = PricingService.metadata(mode) if mode else None
    tariff = Tariff(
        tenant_id=charge_point.tenant_id,
        site_id=charge_point.site_id,
        charge_point_id=charge_point.id if source == "charger" else None,
        name="test tariff",
        base_price_per_kwh=Decimal(price),
        service_fee=Decimal("0.00"),
        time_based_rules=metadata,
        valid_from=datetime.now(timezone.utc) - timedelta(minutes=1),
        valid_until=valid_until,
        is_active=True,
    )
    db.add(tariff)
    db.commit()
    return tariff


def test_legacy_positive_is_paid_and_legacy_zero_is_unavailable(
    db_session, sample_charge_point
):
    _tariff(db_session, sample_charge_point, price="2700.00")
    resolved = PricingService.resolve(
        db_session, sample_charge_point.tenant_id, sample_charge_point.id
    )
    assert resolved.pricing_mode == PricingMode.PAID
    assert resolved.pricing_source == "site"

    db_session.query(Tariff).delete()
    db_session.commit()
    _tariff(db_session, sample_charge_point, price="0.00")
    resolved = PricingService.resolve(
        db_session, sample_charge_point.tenant_id, sample_charge_point.id
    )
    assert resolved.pricing_mode == PricingMode.UNAVAILABLE
    assert not resolved.is_available


def test_explicit_charger_unavailable_overrides_paid_site(db_session, sample_charge_point):
    _tariff(db_session, sample_charge_point, price="2700.00")
    _tariff(
        db_session,
        sample_charge_point,
        price="0.00",
        mode=PricingMode.UNAVAILABLE,
        source="charger",
    )
    resolved = PricingService.resolve(
        db_session, sample_charge_point.tenant_id, sample_charge_point.id
    )
    assert resolved.pricing_mode == PricingMode.UNAVAILABLE
    assert resolved.pricing_source == "charger"


def test_session_start_creates_one_locked_snapshot(
    db_session, sample_charge_point, sample_evse
):
    sample_charge_point.commissioning_status = "commissioned"
    tariff = _tariff(db_session, sample_charge_point, price="2700.00")

    session = SessionService.start_session(
        db_session,
        sample_charge_point.ocpp_identity,
        sample_evse.evse_id,
        1001,
        "TEST-TAG",
        meter_start=1000,
    )
    snapshots = db_session.query(PricingSnapshot).filter_by(session_id=session.id).all()
    assert len(snapshots) == 1
    assert snapshots[0].tariff_id == tariff.id
    assert snapshots[0].price_per_kwh == Decimal("2700.00")

    replay = SessionService.start_session(
        db_session,
        sample_charge_point.ocpp_identity,
        sample_evse.evse_id,
        1001,
        "TEST-TAG",
        meter_start=1000,
    )
    assert replay.id == session.id
    assert db_session.query(PricingSnapshot).filter_by(session_id=session.id).count() == 1


def test_settlement_uses_start_snapshot_after_tariff_change(
    db_session, sample_charge_point, sample_evse
):
    sample_charge_point.commissioning_status = "commissioned"
    _tariff(db_session, sample_charge_point, price="1000.00")
    user = AppUser(
        email="pricing@example.com",
        password_hash="test",
        balance=Decimal("100000.00"),
    )
    db_session.add(user)
    db_session.commit()

    session = SessionService.start_session(
        db_session,
        sample_charge_point.ocpp_identity,
        sample_evse.evse_id,
        1002,
        "TEST-TAG-2",
        user_id=str(user.id),
        meter_start=0,
    )
    db_session.query(Tariff).update({Tariff.is_active: False})
    _tariff(db_session, sample_charge_point, price="9000.00")
    session.end_time = datetime.now(timezone.utc)
    session.meter_stop = 2000
    session.status = "completed"
    db_session.commit()

    result = BillingService.settle_session(db_session, session, user)
    assert result.price_per_kwh == Decimal("1000.00")
    assert result.charged_amount == Decimal("2000.00")
    assert db_session.query(PricingSnapshot).filter_by(session_id=session.id).count() == 1


def test_free_session_settles_zero_without_reducing_balance(
    db_session, sample_charge_point, sample_evse
):
    sample_charge_point.commissioning_status = "commissioned"
    tariff = _tariff(
        db_session,
        sample_charge_point,
        price="0.00",
        mode=PricingMode.FREE,
        valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    tariff.time_based_rules = PricingService.metadata(
        PricingMode.FREE, free_reason="Launch promotion"
    )
    user = AppUser(email="free@example.com", password_hash="test", balance=Decimal("10.00"))
    db_session.add(user)
    db_session.commit()

    session = SessionService.start_session(
        db_session,
        sample_charge_point.ocpp_identity,
        sample_evse.evse_id,
        1003,
        "FREE-TAG",
        user_id=str(user.id),
        meter_start=0,
    )
    session.end_time = datetime.now(timezone.utc)
    session.meter_stop = 50000
    session.status = "completed"
    db_session.commit()

    result = BillingService.settle_session(db_session, session, user)
    assert result.charged_amount == Decimal("0.00")
    assert result.balance == Decimal("10.00")
    assert db_session.query(Payment).filter_by(invoice_id=UUID(result.invoice_id)).count() == 1
    assert db_session.query(AppWalletTransaction).filter_by(
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
    ).count() == 0
