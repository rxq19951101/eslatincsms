"""Focused safety tests for the deterministic SIM-E2E cleanup script."""

import argparse
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.database.models import (
    ChargePoint,
    ChargingSession,
    EVSE,
    Invoice,
    OutboxEvent,
    Payment,
    PricingSnapshot,
    Tariff,
)


def _seed(db_session, monkeypatch, capsys):
    from scripts import seed_sim_e2e

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SIM_E2E_ADMIN_PASSWORD", "admin-seed-password")
    monkeypatch.setenv("SIM_E2E_APP_PASSWORD", "app-seed-password")
    monkeypatch.setenv("SIM_E2E_READONLY_PASSWORD", "readonly-seed-password")
    monkeypatch.setattr(seed_sim_e2e, "SessionLocal", lambda: db_session)
    seed_sim_e2e.main()
    capsys.readouterr()

    session = db_session.query(ChargingSession).filter_by(transaction_id=900001).one()
    tariff = db_session.query(Tariff).filter_by(tenant_id=session.tenant_id).first()
    return session, tariff


def _add_financial_graph(db_session, session, tariff, *, suffix: str):
    snapshot = PricingSnapshot(
        tenant_id=session.tenant_id,
        tariff_id=tariff.id,
        session_id=session.id,
        price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        snapshot_data={"scenario": suffix},
    )
    db_session.add(snapshot)
    db_session.flush()
    invoice = Invoice(
        invoice_number=f"inv_SIM-E2E-{suffix}",
        tenant_id=session.tenant_id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="paid",
    )
    db_session.add(invoice)
    db_session.flush()
    payment = Payment(
        payment_number=f"pay_SIM-E2E-{suffix}",
        tenant_id=session.tenant_id,
        invoice_id=invoice.id,
        amount=Decimal("2700.00"),
        payment_method="wallet",
        payment_provider="app_wallet",
        transaction_id=f"SIM-E2E-{suffix}",
        status="completed",
    )
    db_session.add(payment)
    return invoice, payment


def _add_matched_graph(db_session, session, tariff):
    invoice, payment = _add_financial_graph(
        db_session, session, tariff, suffix="CP_2133209529"
    )
    outboxes = [
        OutboxEvent(
            tenant_id=session.tenant_id,
            aggregate_type="ChargingSession",
            aggregate_id=str(session.id),
            event_type=event_type,
            idempotency_key=f"cleanup-test:{event_type}:{session.id}",
            payload={"session_id": str(session.id)},
        )
        for event_type in ("ChargingSessionStarted", "ChargingSessionCompleted")
    ]
    db_session.add_all(outboxes)
    db_session.commit()
    return invoice, payment, outboxes


def _run_cleanup_main(db_session, monkeypatch, capsys, *, apply: bool):
    from scripts import cleanup_sim_e2e

    monkeypatch.setattr(cleanup_sim_e2e, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        cleanup_sim_e2e,
        "parse_args",
        lambda: argparse.Namespace(apply=apply),
    )
    monkeypatch.setattr(
        cleanup_sim_e2e,
        "ensure_safe_environment",
        lambda requested_apply: "test",
    )
    cleanup_sim_e2e.main()
    return json.loads(capsys.readouterr().out)


def test_cleanup_dry_run_matches_linked_outbox_and_payment(
    db_session, monkeypatch, capsys
):
    session, tariff = _seed(db_session, monkeypatch, capsys)
    invoice, payment, outboxes = _add_matched_graph(db_session, session, tariff)
    invoice_id = invoice.id
    payment_id = payment.id
    outbox_ids = [row.id for row in outboxes]

    report = _run_cleanup_main(
        db_session, monkeypatch, capsys, apply=False
    )

    assert report["mode"] == "dry-run"
    assert report["matched_rows"]["outbox_events"] == 2
    assert report["matched_rows"]["payments"] == 1
    assert report["unmatched_tenant_rows"] == {}
    assert db_session.get(Invoice, invoice_id) is not None
    assert db_session.get(Payment, payment_id) is not None
    assert all(db_session.get(OutboxEvent, row_id) is not None for row_id in outbox_ids)


def test_cleanup_apply_deletes_linked_outbox_and_payment(
    db_session, monkeypatch, capsys
):
    session, tariff = _seed(db_session, monkeypatch, capsys)
    invoice, payment, outboxes = _add_matched_graph(db_session, session, tariff)
    invoice_id = invoice.id
    payment_id = payment.id
    outbox_ids = [row.id for row in outboxes]

    report = _run_cleanup_main(
        db_session, monkeypatch, capsys, apply=True
    )

    assert report["mode"] == "apply"
    assert report["deleted_rows"]["outbox_events"] == 2
    assert report["deleted_rows"]["payments"] == 1
    assert report["remaining"] == {}
    assert db_session.get(Invoice, invoice_id) is None
    assert db_session.get(Payment, payment_id) is None
    assert all(db_session.get(OutboxEvent, row_id) is None for row_id in outbox_ids)


def test_cleanup_refuses_unrelated_prefixed_payment_and_outbox(
    db_session, monkeypatch, capsys
):
    from scripts import cleanup_sim_e2e

    matched_session, tariff = _seed(db_session, monkeypatch, capsys)
    matched_invoice, matched_payment, _ = _add_matched_graph(
        db_session, matched_session, tariff
    )

    charge_point = db_session.query(ChargePoint).filter_by(
        ocpp_identity="SIM-E2E-CP-OTHER-001"
    ).one()
    evse = db_session.query(EVSE).filter_by(charge_point_id=charge_point.id).one()
    unrelated_session = ChargingSession(
        tenant_id=charge_point.tenant_id,
        evse_id=evse.id,
        charge_point_id=charge_point.id,
        transaction_id=2133209530,
        id_tag="NON-SIM-OWNER",
        user_id=str(uuid.uuid4()),
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        meter_start=0,
        meter_stop=1000,
        status="completed",
    )
    db_session.add(unrelated_session)
    db_session.flush()
    unrelated_invoice, unrelated_payment = _add_financial_graph(
        db_session,
        unrelated_session,
        tariff,
        suffix="UNRELATED-PREFIX-ONLY",
    )
    unrelated_outbox = OutboxEvent(
        tenant_id=charge_point.tenant_id,
        aggregate_type="ChargingSession",
        aggregate_id=str(unrelated_session.id),
        event_type="ChargingSessionCompleted",
        idempotency_key=f"unrelated:{unrelated_session.id}",
        payload={"session_id": str(unrelated_session.id)},
    )
    db_session.add(unrelated_outbox)
    db_session.commit()
    matched_invoice_id = matched_invoice.id
    matched_payment_id = matched_payment.id
    unrelated_payment_id = unrelated_payment.id
    unrelated_outbox_id = unrelated_outbox.id

    session_ids = cleanup_sim_e2e.discover_sim_session_ids(db_session)
    invoice_ids = cleanup_sim_e2e.discover_sim_invoice_ids(db_session, session_ids)
    assert unrelated_session.id not in session_ids
    assert unrelated_invoice.id not in invoice_ids
    unmatched = cleanup_sim_e2e.unmatched_tenant_counts(
        db_session, session_ids, invoice_ids
    )
    assert unmatched["outbox_events"] >= 1
    assert unmatched["payments"] >= 1

    with pytest.raises(RuntimeError, match="non-whitelisted rows"):
        _run_cleanup_main(db_session, monkeypatch, capsys, apply=True)

    assert db_session.get(Payment, matched_payment_id) is not None
    assert db_session.get(Invoice, matched_invoice_id) is not None
    assert db_session.get(Payment, unrelated_payment_id) is not None
    assert db_session.get(OutboxEvent, unrelated_outbox_id) is not None
