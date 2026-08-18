"""Direct BE-203 evaluator, recheck and admission-preflight coverage."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.database.models import (
    AppUser,
    ChargebackCase,
    ChargingSession,
    FinancialEligibilityDecision,
    Invoice,
    PaymentAllocation,
    QrToken,
    ReconciliationItem,
    ReconciliationRun,
    RecoveryAttempt,
    RefundCase,
    RuntimeRailControl,
    Tariff,
    PricingSnapshot,
    OutboxEvent,
)
from app.services.financial_eligibility import (
    ChargingAdmissionPreflight,
    FinancialEligibilityEvaluator,
    enqueue_financial_eligibility_recheck,
)
from app.services.pricing_service import PricingService


def _facts(db, tenant, charge_point, evse, *, email="be203@example.test", balance="0.00"):
    now = datetime.now(timezone.utc)
    user = AppUser(email=email, password_hash="test", balance=Decimal(balance))
    db.add(user)
    db.flush()
    session = ChargingSession(
        tenant_id=tenant.id,
        evse_id=evse.id,
        charge_point_id=charge_point.id,
        transaction_id=200300 + db.query(ChargingSession).count(),
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=now,
        end_time=now,
        status="completed",
        payment_status="unpaid",
    )
    tariff = Tariff(
        tenant_id=tenant.id,
        site_id=charge_point.site_id,
        charge_point_id=charge_point.id,
        name="BE-203 tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=now,
        is_active=True,
        time_based_rules=PricingService.metadata("paid"),
    )
    db.add_all([session, tariff])
    db.flush()
    snapshot = PricingSnapshot(
        tenant_id=tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
    )
    db.add(snapshot)
    db.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db.add(invoice)
    db.commit()
    return user, session, invoice


def _attempt(db, user, session, invoice, *, status="allocated"):
    attempt = RecoveryAttempt(
        tenant_id=invoice.tenant_id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        session_id=session.id,
        attempt_number=1,
        method="wallet",
        target_amount=Decimal("2700.00"),
        allocated_amount=Decimal("2700.00") if status == "allocated" else Decimal("0.00"),
        currency="COP",
        status=status,
        idempotency_key=f"be203:{uuid4()}",
        request_fingerprint="be203-fingerprint",
        audit_reference="be203-attempt",
    )
    db.add(attempt)
    db.flush()
    return attempt


def _allocation(db, attempt, *, status="committed"):
    allocation = PaymentAllocation(
        tenant_id=attempt.tenant_id,
        invoice_id=attempt.invoice_id,
        recovery_attempt_id=attempt.id,
        method="wallet",
        provider="app_wallet",
        amount=Decimal("2700.00"),
        currency="COP",
        status=status,
        audit_reference="be203-allocation",
    )
    db.add(allocation)
    db.flush()
    return allocation


def test_evaluator_is_fail_closed_and_rebuilds_after_allocation(db_session, sample_tenant, sample_charge_point, sample_evse):
    user, session, invoice = _facts(db_session, sample_tenant, sample_charge_point, sample_evse)

    first = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert first.status == "blocked"
    assert first.reason_codes == ("open_invoice",)
    assert first.decision_version == 1
    assert first.source_watermark.startswith("financial-facts:")

    attempt = _attempt(db_session, user, session, invoice, status="processing")
    db_session.commit()
    processing = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert processing.status == "recheck_required"
    assert "recovery_processing" in processing.reason_codes

    attempt.status = "unknown"
    db_session.commit()
    unknown = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert unknown.status == "unknown"
    assert "recovery_unknown" in unknown.reason_codes

    attempt.status = "allocated"
    allocation = _allocation(db_session, attempt)
    db_session.commit()
    eligible = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert eligible.status == "eligible"
    assert eligible.reason_codes == ()
    assert eligible.decision_version > unknown.decision_version
    assert db_session.get(FinancialEligibilityDecision, db_session.query(FinancialEligibilityDecision).one().id).status == "eligible"
    assert allocation.status == "committed"


def test_refund_and_reconciliation_facts_reblock_and_recheck_event_is_idempotent(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, session, invoice = _facts(
        db_session, sample_tenant, sample_charge_point, sample_evse, email="be203-facts@example.test"
    )
    attempt = _attempt(db_session, user, session, invoice)
    allocation = _allocation(db_session, attempt)
    db_session.commit()
    assert FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id).status == "eligible"

    allocation.status = "reversed"
    db_session.commit()
    reversed_result = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert reversed_result.status == "blocked"
    assert "refund_or_chargeback" in reversed_result.reason_codes
    allocation.status = "committed"
    db_session.commit()

    chargeback = ChargebackCase(
        tenant_id=invoice.tenant_id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        provider="mercadopago",
        provider_account_ref="platform:eslatin",
        provider_dispute_ref="be203-dispute",
        disputed_amount=Decimal("2700.00"),
        currency="COP",
        status="unknown",
        received_at=datetime.now(timezone.utc),
        audit_reference="be203-chargeback",
    )
    db_session.add(chargeback)
    db_session.commit()
    unknown_funds = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert unknown_funds.status == "unknown"
    assert "refund_or_chargeback" in unknown_funds.reason_codes
    chargeback.status = "reversed"
    db_session.commit()

    refund = RefundCase(
        tenant_id=invoice.tenant_id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        requested_amount=Decimal("2700.00"),
        approved_amount=Decimal("2700.00"),
        refunded_amount=Decimal("2700.00"),
        currency="COP",
        reason_code="customer_request",
        status="refunded",
        audit_reference="be203-refund",
    )
    db_session.add(refund)
    db_session.commit()
    reblocked = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert reblocked.status == "blocked"
    assert reblocked.reason_codes == ("refund_or_chargeback",)

    run = ReconciliationRun(
        scope_type="tenant",
        scope_ref=f"tenant:{invoice.tenant_id}",
        tenant_id=invoice.tenant_id,
        provider="mercadopago",
        provider_account_ref="platform:eslatin",
        business_date=datetime.now(timezone.utc).date(),
        source_checksum="be203-run",
        audit_reference="be203-run-audit",
    )
    db_session.add(run)
    db_session.flush()
    item = ReconciliationItem(
        reconciliation_run_id=run.id,
        scope_type="tenant",
        scope_ref=f"tenant:{invoice.tenant_id}",
        tenant_id=invoice.tenant_id,
        provider="mercadopago",
        source_reference="be203-item",
        payment_allocation_id=allocation.id,
        expected_amount=Decimal("2700.00"),
        observed_amount=Decimal("2600.00"),
        currency="COP",
        status="mismatch",
        mismatch_code="amount_mismatch",
        source_fingerprint="be203-item-fingerprint",
        occurred_at=datetime.now(timezone.utc),
        audit_reference="be203-item-audit",
    )
    db_session.add(item)
    db_session.commit()
    mismatch = FinancialEligibilityEvaluator.evaluate(db_session, app_user_id=user.id)
    assert "reconciliation_mismatch" in mismatch.reason_codes

    enqueue_financial_eligibility_recheck(
        db_session,
        app_user_id=user.id,
        tenant_id=invoice.tenant_id,
        source_type="payment_allocation",
        source_id=allocation.id,
        source_version=1,
        reason_code="allocation_changed",
    )
    enqueue_financial_eligibility_recheck(
        db_session,
        app_user_id=user.id,
        tenant_id=invoice.tenant_id,
        source_type="payment_allocation",
        source_id=allocation.id,
        source_version=1,
        reason_code="allocation_changed",
    )
    db_session.commit()
    events = db_session.query(OutboxEvent).filter(
        OutboxEvent.event_type == "financial.eligibility.recheck_requested",
        OutboxEvent.aggregate_id == str(user.id),
    ).all()
    assert len(events) == 1
    assert events[0].scope_ref == f"tenant:{invoice.tenant_id}"


def test_preflight_composes_rail_without_leaking_rail_closed_into_financial_eligibility(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user, _, _ = _facts(
        db_session, sample_tenant, sample_charge_point, sample_evse, email="be203-preflight@example.test"
    )
    invoice = db_session.query(Invoice).filter(Invoice.session_id == db_session.query(ChargingSession).filter(ChargingSession.app_user_id == user.id).one().id).one()
    invoice.status = "paid"
    session = db_session.query(ChargingSession).filter(ChargingSession.app_user_id == user.id).one()
    session.payment_status = "paid"
    qr = QrToken(
        token="be203-preflight-qr-token",
        operator_tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )
    rail = RuntimeRailControl(
        axis="paid_admission",
        scope_type="platform",
        scope_ref="platform:eslatin",
        status="closed",
        reason_code="incident",
        audit_reference="be203-rail",
    )
    db_session.add_all([qr, rail])
    db_session.commit()

    result = ChargingAdmissionPreflight.evaluate(
        db_session,
        app_user_id=user.id,
        qr_token=qr.token,
        settlement_method="wallet",
    )
    assert result.decision == "blocked"
    assert result.rail_eligibility.status == "closed"
    assert result.financial_eligibility.status == "eligible"
    assert "rail_closed" not in result.financial_eligibility.reason_codes

    rail.status = "unknown"
    db_session.commit()
    unknown = ChargingAdmissionPreflight.evaluate(
        db_session,
        app_user_id=user.id,
        qr_token=qr.token,
        settlement_method="wallet",
    )
    assert unknown.decision == "blocked"
    assert unknown.rail_eligibility.status == "unknown"
    assert unknown.financial_eligibility.status == "eligible"
