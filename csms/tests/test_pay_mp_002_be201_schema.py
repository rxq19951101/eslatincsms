"""Direct BE-201 schema, ownership, and dirty-data tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import DateTime, Numeric, inspect, text
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from app.database.models import (
    AppUser,
    ChargebackCase,
    ChargePoint,
    ChargingSession,
    EVSE,
    FinancialEligibilityDecision,
    Invoice,
    OutboxEvent,
    PaymentAllocation,
    PricingSnapshot,
    ReconciliationException,
    ReconciliationItem,
    ReconciliationRun,
    RecoveryAttempt,
    RefundApproval,
    RefundAttempt,
    RefundCase,
    RuntimeRailControl,
    Site,
    SupportCase,
    SupportCaseEvent,
    Tariff,
    Tenant,
    Base,
)


BE201_TABLES = {
    "recovery_attempts",
    "payment_allocations",
    "financial_eligibility_decisions",
    "refund_cases",
    "refund_approvals",
    "refund_attempts",
    "chargeback_cases",
    "reconciliation_runs",
    "reconciliation_items",
    "reconciliation_exceptions",
    "runtime_rail_controls",
    "support_cases",
    "support_case_events",
}


BE201_CURRENCY_CHECKS = {
    "recovery_attempts": "ck_recovery_attempt_currency",
    "payment_allocations": "ck_payment_allocation_currency",
    "refund_cases": "ck_refund_case_currency",
    "refund_approvals": "ck_refund_approval_currency",
    "refund_attempts": "ck_refund_attempt_currency",
    "chargeback_cases": "ck_chargeback_currency",
    "reconciliation_items": "ck_reconciliation_item_currency",
}


def _enable_foreign_keys(db_session) -> None:
    db_session.execute(text("PRAGMA foreign_keys=ON"))


def _invoice_fixture(
    db_session,
    sample_tenant,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    user = AppUser(
        email=f"be201-{uuid4().hex}@example.test",
        password_hash="not-a-real-password-hash",
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    now = datetime.now(timezone.utc)
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_commercial_charge_point.id,
        transaction_id=int(uuid4().int % 1_000_000_000),
        id_tag=f"BE201{uuid4().hex[:16]}",
        app_user_id=user.id,
        start_time=now - timedelta(minutes=10),
        end_time=now,
        meter_start=0,
        meter_stop=1000,
        status="completed",
        payment_status="unpaid",
    )
    db_session.add(session)
    db_session.flush()
    tariff = db_session.query(Tariff).filter(Tariff.site_id == sample_site.id).one()
    snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
    )
    db_session.add(snapshot)
    db_session.flush()
    invoice = Invoice(
        tenant_id=sample_tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("1.000"),
        duration_minutes=Decimal("10.00"),
        energy_cost=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("2700.00"),
        status="pending",
    )
    db_session.add(invoice)
    db_session.commit()
    return user, session, invoice


def _attempt(user, session, invoice, *, attempt_number=1, key=None, status="created"):
    return RecoveryAttempt(
        tenant_id=invoice.tenant_id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        session_id=session.id,
        attempt_number=attempt_number,
        method="new_card",
        provider="mercadopago",
        provider_account_ref="merchant:test",
        provider_operation_key=f"provider-op-{uuid4().hex}",
        target_amount=Decimal("2700.00"),
        allocated_amount=Decimal("0.00"),
        currency="COP",
        status=status,
        idempotency_key=key or f"recovery-{uuid4().hex}",
        request_fingerprint=uuid4().hex,
        audit_reference=f"audit:{uuid4()}",
    )


def _postgres_invoice_bundle(db_session, label: str):
    tenant = Tenant(name=f"BE-201 PG {label} {uuid4().hex}", status="active")
    db_session.add(tenant)
    db_session.flush()
    site = Site(
        tenant_id=tenant.id,
        name=f"BE-201 {label} site",
        address=f"Bogota BE-201 {label} address",
        latitude=4.711,
        longitude=-74.0721,
    )
    db_session.add(site)
    db_session.flush()
    charge_point = ChargePoint(
        tenant_id=tenant.id,
        site_id=site.id,
        ocpp_identity=f"BE201-{label}-{uuid4().hex[:10]}",
        display_code=f"P{uuid4().hex[:7].upper()}",
        commissioning_status="commissioned",
    )
    db_session.add(charge_point)
    db_session.flush()
    evse = EVSE(
        tenant_id=tenant.id,
        charge_point_id=charge_point.id,
        evse_id=1,
        connector_type="Type2",
        max_power_kw=Decimal("7.0"),
    )
    tariff = Tariff(
        tenant_id=tenant.id,
        site_id=site.id,
        name=f"BE-201 {label} tariff",
        base_price_per_kwh=Decimal("2700.00"),
        service_fee=Decimal("0.00"),
        valid_from=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add_all([evse, tariff])
    db_session.commit()
    user, charging_session, invoice = _invoice_fixture(
        db_session,
        tenant,
        site,
        charge_point,
        evse,
    )
    attempt = _attempt(user, charging_session, invoice)
    db_session.add(attempt)
    db_session.flush()
    allocation = PaymentAllocation(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        recovery_attempt_id=attempt.id,
        method="new_card",
        provider="mercadopago",
        amount=Decimal("2700.00"),
        currency="COP",
        status="pending",
        audit_reference=f"audit:{uuid4()}",
    )
    db_session.add(allocation)
    db_session.commit()
    return tenant, allocation


def _postgres_support_resources(db_session, label: str):
    tenant, allocation = _postgres_invoice_bundle(db_session, label)
    attempt = db_session.get(RecoveryAttempt, allocation.recovery_attempt_id)
    invoice = db_session.get(Invoice, allocation.invoice_id)
    charging_session = db_session.get(ChargingSession, invoice.session_id)
    user = db_session.get(AppUser, attempt.app_user_id)
    refund_case = RefundCase(
        tenant_id=tenant.id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        requested_amount=Decimal("2700.00"),
        approved_amount=Decimal("0.00"),
        refunded_amount=Decimal("0.00"),
        currency="COP",
        reason_code="support-regression",
        audit_reference=f"audit:{uuid4()}",
    )
    chargeback_case = ChargebackCase(
        tenant_id=tenant.id,
        app_user_id=user.id,
        invoice_id=invoice.id,
        payment_allocation_id=allocation.id,
        provider="mercadopago",
        provider_account_ref="merchant:test",
        provider_dispute_ref=f"dispute:{uuid4()}",
        disputed_amount=Decimal("2700.00"),
        currency="COP",
        audit_reference=f"audit:{uuid4()}",
        received_at=datetime.now(timezone.utc),
    )
    tenant_rail = RuntimeRailControl(
        axis="paid_admission",
        scope_type="tenant",
        scope_ref=f"tenant:{tenant.id}",
        tenant_id=tenant.id,
        status="open",
        audit_reference=f"audit:{uuid4()}",
    )
    platform_rail = (
        db_session.query(RuntimeRailControl)
        .filter(
            RuntimeRailControl.axis == "payment_creation",
            RuntimeRailControl.scope_type == "platform",
            RuntimeRailControl.scope_ref == "platform:eslatin",
        )
        .one_or_none()
    )
    new_facts = [refund_case, chargeback_case, tenant_rail]
    if platform_rail is None:
        platform_rail = RuntimeRailControl(
            axis="payment_creation",
            scope_type="platform",
            scope_ref="platform:eslatin",
            tenant_id=None,
            status="open",
            audit_reference=f"audit:{uuid4()}",
        )
        new_facts.append(platform_rail)
    db_session.add_all(new_facts)
    db_session.commit()
    return {
        "tenant": tenant,
        "user": user,
        "invoice": invoice,
        "session": charging_session,
        "refund_case": refund_case,
        "chargeback_case": chargeback_case,
        "tenant_rail": tenant_rail,
        "platform_rail": platform_rail,
    }


def _assert_postgresql_fk_rejected(db_session, instance, constraint_name: str) -> None:
    db_session.add(instance)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()
    sqlstate = getattr(exc_info.value.orig, "sqlstate", None) or getattr(
        exc_info.value.orig, "pgcode", None
    )
    assert sqlstate == "23503"
    assert constraint_name in str(exc_info.value.orig)
    db_session.rollback()


def _run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    # alembic.env feeds DATABASE_URL through ConfigParser; URL-encoded query
    # parameters therefore need percent escaping at that boundary.
    environment["DATABASE_URL"] = database_url.replace("%", "%%")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=Path(__file__).parents[1],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_be201_metadata_has_typed_tables_constraints_and_no_risk_ledger():
    metadata = RecoveryAttempt.metadata
    assert BE201_TABLES <= set(metadata.tables)
    assert "risk_ledger" not in metadata.tables
    assert "risk_ledgers" not in metadata.tables

    recovery = metadata.tables["recovery_attempts"]
    allocation = metadata.tables["payment_allocations"]
    assert isinstance(recovery.c.target_amount.type, Numeric)
    assert recovery.c.target_amount.type.scale == 2
    assert isinstance(recovery.c.created_at.type, DateTime)
    assert recovery.c.created_at.type.timezone is True
    assert recovery.c.schema_version.nullable is False
    assert allocation.c.audit_reference.nullable is False

    recovery_uniques = {c.name for c in recovery.constraints if c.name}
    assert "uq_recovery_attempt_user_idempotency" in recovery_uniques
    assert "fk_recovery_attempt_invoice_owner" in recovery_uniques
    allocation_indexes = {index.name for index in allocation.indexes}
    assert "uq_payment_allocation_committed_invoice" in allocation_indexes
    allocation_constraints = {c.name for c in allocation.constraints if c.name}
    assert "uq_payment_allocation_id_tenant" in allocation_constraints

    reconciliation_item = metadata.tables["reconciliation_items"]
    reconciliation_item_constraints = {
        c.name for c in reconciliation_item.constraints if c.name
    }
    assert "fk_reconciliation_item_allocation_owner" in reconciliation_item_constraints

    expected_support_constraints = {
        "fk_support_case_invoice_owner",
        "fk_support_case_session_owner",
        "fk_support_case_refund_owner",
        "fk_support_case_chargeback_owner",
        "fk_support_case_rail_owner",
        "uq_support_case_id_tenant",
    }
    support_constraints = {
        c.name
        for c in metadata.tables["support_cases"].constraints
        if c.name
    }
    assert expected_support_constraints <= support_constraints
    event_constraints = {
        c.name
        for c in metadata.tables["support_case_events"].constraints
        if c.name
    }
    assert "fk_support_case_event_owner" in event_constraints
    for table_name, unique_name in {
        "invoices": "uq_invoices_id_tenant",
        "charging_sessions": "uq_charging_sessions_id_tenant",
        "refund_cases": "uq_refund_case_id_tenant",
        "chargeback_cases": "uq_chargeback_case_id_tenant",
        "runtime_rail_controls": "uq_runtime_rail_control_id_tenant",
    }.items():
        constraints = {
            c.name for c in metadata.tables[table_name].constraints if c.name
        }
        assert unique_name in constraints

    reconciliation_exception = metadata.tables["reconciliation_exceptions"]
    reconciliation_exception_constraints = {
        c.name for c in reconciliation_exception.constraints if c.name
    }
    assert "fk_reconciliation_exception_item_run" in reconciliation_exception_constraints
    assert "fk_reconciliation_exception_run_scope" in reconciliation_exception_constraints

    outbox = metadata.tables["outbox_events"]
    assert outbox.c.tenant_id.nullable is True
    assert outbox.c.scope_type.nullable is False
    assert outbox.c.scope_ref.nullable is False
    outbox_constraints = {c.name for c in outbox.constraints if c.name}
    assert "ck_outbox_scope_ownership" in outbox_constraints
    assert "uq_outbox_scope_idempotency" in outbox_constraints
    assert "uq_outbox_tenant_idempotency" not in outbox_constraints

    for table_name, constraint_name in BE201_CURRENCY_CHECKS.items():
        constraints = {
            constraint.name: str(constraint.sqltext)
            for constraint in metadata.tables[table_name].constraints
            if constraint.name and hasattr(constraint, "sqltext")
        }
        assert constraints[constraint_name] == "currency = 'COP'"


def test_recovery_attempt_rejects_dirty_amount_status_idempotency_and_owner(
    db_session,
    sample_tenant,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    _enable_foreign_keys(db_session)
    user, session, invoice = _invoice_fixture(
        db_session,
        sample_tenant,
        sample_site,
        sample_commercial_charge_point,
        sample_evse,
    )
    attempt = _attempt(user, session, invoice, key="stable-idempotency")
    db_session.add(attempt)
    db_session.commit()

    duplicate = _attempt(
        user,
        session,
        invoice,
        attempt_number=2,
        key="stable-idempotency",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    invalid_amount = _attempt(user, session, invoice, attempt_number=2)
    invalid_amount.target_amount = Decimal("-1.00")
    db_session.add(invalid_amount)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    invalid_status = _attempt(user, session, invoice, attempt_number=2, status="provider_magic")
    db_session.add(invalid_status)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    invalid_currency = _attempt(user, session, invoice, attempt_number=2)
    invalid_currency.currency = "USD"
    db_session.add(invalid_currency)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    other_tenant = Tenant(name="BE-201 other tenant", status="active")
    db_session.add(other_tenant)
    db_session.commit()
    wrong_owner = _attempt(user, session, invoice, attempt_number=2)
    wrong_owner.tenant_id = other_tenant.id
    db_session.add(wrong_owner)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_payment_allocation_allows_only_one_committed_invoice_winner(
    db_session,
    sample_tenant,
    sample_site,
    sample_commercial_charge_point,
    sample_evse,
):
    _enable_foreign_keys(db_session)
    user, session, invoice = _invoice_fixture(
        db_session,
        sample_tenant,
        sample_site,
        sample_commercial_charge_point,
        sample_evse,
    )
    first = _attempt(user, session, invoice, attempt_number=1)
    second = _attempt(user, session, invoice, attempt_number=2)
    db_session.add_all([first, second])
    db_session.commit()

    winner = PaymentAllocation(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        recovery_attempt_id=first.id,
        method="new_card",
        provider="mercadopago",
        amount=Decimal("2700.00"),
        currency="COP",
        status="committed",
        committed_at=datetime.now(timezone.utc),
        audit_reference=f"audit:{uuid4()}",
    )
    db_session.add(winner)
    db_session.commit()

    duplicate_winner = PaymentAllocation(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        recovery_attempt_id=second.id,
        method="new_card",
        provider="mercadopago",
        amount=Decimal("2700.00"),
        currency="COP",
        status="committed",
        committed_at=datetime.now(timezone.utc),
        audit_reference=f"audit:{uuid4()}",
    )
    db_session.add(duplicate_winner)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.query(PaymentAllocation).filter_by(invoice_id=invoice.id).count() == 1


def test_outbox_scope_is_canonical_platform_or_owned_tenant(db_session, sample_tenant):
    _enable_foreign_keys(db_session)
    tenant_event = OutboxEvent(
        tenant_id=sample_tenant.id,
        aggregate_type="invoice",
        aggregate_id=str(uuid4()),
        event_type="invoice.changed",
        idempotency_key="tenant-event",
        payload={"schema_version": 1},
    )
    platform_event = OutboxEvent(
        tenant_id=None,
        scope_type="platform",
        scope_ref="platform:eslatin",
        aggregate_type="rail",
        aggregate_id="platform:eslatin",
        event_type="rail.control.closed",
        idempotency_key="platform-event",
        payload={"schema_version": 1},
    )
    db_session.add_all([tenant_event, platform_event])
    db_session.commit()
    assert tenant_event.scope_ref == f"tenant:{sample_tenant.id}"

    fake_platform_tenant = OutboxEvent(
        tenant_id=sample_tenant.id,
        scope_type="platform",
        scope_ref="platform:eslatin",
        aggregate_type="rail",
        aggregate_id="platform:eslatin",
        event_type="rail.control.closed",
        idempotency_key="invalid-platform",
        payload={},
    )
    db_session.add(fake_platform_tenant)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    mismatched_tenant = OutboxEvent(
        tenant_id=sample_tenant.id,
        scope_type="tenant",
        scope_ref=f"tenant:{uuid4()}",
        aggregate_type="invoice",
        aggregate_id=str(uuid4()),
        event_type="invoice.changed",
        idempotency_key="invalid-tenant",
        payload={},
    )
    db_session.add(mismatched_tenant)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    duplicate_key = OutboxEvent(
        tenant_id=None,
        scope_type="platform",
        scope_ref="platform:eslatin",
        aggregate_type="rail",
        aggregate_id="platform:eslatin",
        event_type="rail.control.closed",
        idempotency_key="platform-event",
        payload={},
    )
    db_session.add(duplicate_key)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_all_be201_fact_tables_expose_schema_version_audit_and_utc():
    for model in (
        RecoveryAttempt,
        PaymentAllocation,
        FinancialEligibilityDecision,
        RefundCase,
        RefundApproval,
        RefundAttempt,
        ChargebackCase,
        ReconciliationRun,
        ReconciliationItem,
        ReconciliationException,
        RuntimeRailControl,
        SupportCase,
        SupportCaseEvent,
    ):
        table = inspect(model).local_table
        assert table.c.schema_version.nullable is False
        assert table.c.audit_reference.nullable is False
        for column_name in ("created_at", "updated_at"):
            column = table.c[column_name]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True


def test_be201_postgresql_ddl_compiles_for_every_typed_table():
    for table_name in BE201_TABLES | {"outbox_events", "invoices"}:
        ddl = str(
            CreateTable(Base.metadata.tables[table_name]).compile(
                dialect=postgresql.dialect()
            )
        )
        assert "CREATE TABLE" in ddl


def test_be201_migration_is_idempotent_on_empty_baseline():
    """Migration 001 builds current metadata; revision 012 must then be a no-op."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "012_pay_mp_002_be201_typed_facts.py"
    )
    spec = importlib.util.spec_from_file_location("be201_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        tables = set(inspect(connection).get_table_names())

    assert BE201_TABLES <= tables
    assert {"scope_type", "scope_ref", "tenant_id"} <= {
        column["name"] for column in inspect(engine).get_columns("outbox_events")
    }


@pytest.mark.skipif(
    not os.environ.get("BE201_POSTGRES_TEST_URL"),
    reason="BE201_POSTGRES_TEST_URL is required for the real P001 migration regression",
)
def test_postgresql_real_p001_shape_upgrade_repeat_partial_and_rollback():
    """Close BE201-QA-004 against a real pre-BE-201 revision-011 shape."""
    admin_engine = create_engine(os.environ["BE201_POSTGRES_TEST_URL"])
    schema_name = f"be201_fix004_{uuid4().hex}"
    base_url = make_url(os.environ["BE201_POSTGRES_TEST_URL"])
    schema_url = base_url.update_query_dict(
        {"options": f"-csearch_path={schema_name}"}
    ).render_as_string(hide_password=False)
    schema_engine = create_engine(schema_url)
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "012_pay_mp_002_be201_typed_facts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "be201_real_p001_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))

        with schema_engine.begin() as connection:
            Base.metadata.create_all(connection)
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES ('011_app_wallet_invoice_link')"
                )
            )

            # Revision 001 imports current metadata, so remove every future
            # BE-201 artifact to reproduce the actual pre-BE-201 P001 shape.
            for table_name in reversed(migration.BE201_TABLES):
                connection.execute(text(f"DROP TABLE {table_name} CASCADE"))
            connection.execute(
                text(
                    "ALTER TABLE invoices DROP CONSTRAINT "
                    "IF EXISTS uq_invoices_id_tenant"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE charging_sessions DROP CONSTRAINT "
                    "IF EXISTS uq_charging_sessions_id_tenant"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE outbox_events DROP CONSTRAINT "
                    "IF EXISTS uq_outbox_scope_idempotency"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE outbox_events DROP CONSTRAINT "
                    "IF EXISTS ck_outbox_scope_ownership"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE outbox_events ALTER COLUMN tenant_id SET NOT NULL"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE outbox_events DROP COLUMN scope_type, "
                    "DROP COLUMN scope_ref"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE outbox_events ADD CONSTRAINT "
                    "uq_outbox_tenant_idempotency "
                    "UNIQUE (tenant_id, idempotency_key)"
                )
            )
            tenant_id = uuid4()
            connection.execute(
                text(
                    "INSERT INTO tenants "
                    "(id, name, status, subscription_plan, max_charge_points, "
                    "max_users, settings, created_at, updated_at) "
                    "VALUES (:id, 'BE-201 real P001', 'active', 'free', 10, 100, "
                    "'{}'::jsonb, now(), now())"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO outbox_events "
                    "(id, tenant_id, aggregate_type, aggregate_id, event_type, "
                    "idempotency_key, payload, status, attempts, available_at, "
                    "created_at) VALUES (:id, :tenant_id, 'legacy', 'p001', "
                    "'legacy.created', 'fix004-old-outbox', '{}'::jsonb, "
                    "'pending', 0, now(), now())"
                ),
                {"id": uuid4(), "tenant_id": tenant_id},
            )

        first_upgrade = _run_alembic(schema_url, "upgrade", "head")
        assert first_upgrade.returncode == 0, first_upgrade.stderr
        with schema_engine.begin() as connection:
            inspector = inspect(connection)
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "012_pay_mp_002_be201"
            assert set(migration.BE201_TABLES) <= set(inspector.get_table_names())
            assert connection.execute(
                text(
                    "SELECT scope_type, scope_ref FROM outbox_events "
                    "WHERE idempotency_key = 'fix004-old-outbox'"
                )
            ).one() == ("tenant", f"tenant:{tenant_id}")
            connection.execute(
                text(
                    "INSERT INTO outbox_events "
                    "(id, tenant_id, aggregate_type, aggregate_id, event_type, "
                    "idempotency_key, payload, status, attempts, available_at, "
                    "created_at) VALUES (:id, :tenant_id, 'legacy', 'p001', "
                    "'legacy.created', 'fix004-old-column-insert', '{}'::jsonb, "
                    "'pending', 0, now(), now())"
                ),
                {"id": uuid4(), "tenant_id": tenant_id},
            )
            assert connection.execute(
                text(
                    "SELECT scope_type FROM outbox_events "
                    "WHERE idempotency_key = 'fix004-old-column-insert'"
                )
            ).scalar_one() == "tenant"

        repeated = _run_alembic(schema_url, "upgrade", "head")
        assert repeated.returncode == 0, repeated.stderr

        downgraded = _run_alembic(
            schema_url, "downgrade", "011_app_wallet_invoice_link"
        )
        assert downgraded.returncode == 0, downgraded.stderr
        with schema_engine.begin() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "011_app_wallet_invoice_link"
            assert set(migration.BE201_TABLES) <= set(
                inspect(connection).get_table_names()
            )

        re_upgraded = _run_alembic(schema_url, "upgrade", "head")
        assert re_upgraded.returncode == 0, re_upgraded.stderr

        # Simulate a partial 012 application and invoke the migration body: the
        # missing target key must be restored before its owner FK, once only.
        with schema_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE support_cases DROP CONSTRAINT "
                    "fk_support_case_rail_owner"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE runtime_rail_controls DROP CONSTRAINT "
                    "uq_runtime_rail_control_id_tenant"
                )
            )
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            migration.upgrade()
            deployed = dict(
                connection.execute(
                    text(
                        "SELECT conname, count(*) FROM pg_constraint "
                        "WHERE conname IN "
                        "('uq_runtime_rail_control_id_tenant', "
                        "'fk_support_case_rail_owner') "
                        "AND connamespace = current_schema()::regnamespace "
                        "GROUP BY conname"
                    )
                ).all()
            )
            assert deployed == {
                "uq_runtime_rail_control_id_tenant": 1,
                "fk_support_case_rail_owner": 1,
            }
            assert connection.execute(
                text("SELECT count(*) FROM alembic_version")
            ).scalar_one() == 1
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "012_pay_mp_002_be201"
    finally:
        schema_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("BE201_POSTGRES_TEST_URL"),
    reason="BE201_POSTGRES_TEST_URL is required for the PostgreSQL constraint regression",
)
def test_postgresql_rejects_wrong_currency_with_sqlstate_23514():
    """Validate all deployed COP checks and reproduce the original QA write."""
    engine = create_engine(os.environ["BE201_POSTGRES_TEST_URL"])
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session = session_factory()
    try:
        deployed = dict(
            db_session.execute(
                text(
                    """
                    SELECT conname, pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conname IN (
                        'ck_recovery_attempt_currency',
                        'ck_payment_allocation_currency',
                        'ck_refund_case_currency',
                        'ck_refund_approval_currency',
                        'ck_refund_attempt_currency',
                        'ck_chargeback_currency',
                        'ck_reconciliation_item_currency'
                    )
                    """
                )
            ).all()
        )
        assert set(deployed) == set(BE201_CURRENCY_CHECKS.values())
        for definition in deployed.values():
            assert "COP" in definition
            assert "upper" not in definition.lower()

        tenant, allocation = _postgres_invoice_bundle(db_session, "currency")
        attempt = db_session.get(RecoveryAttempt, allocation.recovery_attempt_id)
        invoice = db_session.get(Invoice, allocation.invoice_id)
        charging_session = db_session.get(ChargingSession, invoice.session_id)
        user = db_session.get(AppUser, attempt.app_user_id)
        wrong_currency = _attempt(user, charging_session, invoice)
        wrong_currency.currency = "USD"
        db_session.add(wrong_currency)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()

        sqlstate = getattr(exc_info.value.orig, "sqlstate", None) or getattr(
            exc_info.value.orig, "pgcode", None
        )
        assert sqlstate == "23514"
        assert "ck_recovery_attempt_currency" in str(exc_info.value.orig)
    finally:
        db_session.rollback()
        db_session.close()
        engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("BE201_POSTGRES_TEST_URL"),
    reason="BE201_POSTGRES_TEST_URL is required for the PostgreSQL ownership regression",
)
def test_postgresql_reconciliation_allocation_tenant_ownership():
    """Close BE201-QA-002 while preserving legal platform reconciliation."""
    engine = create_engine(os.environ["BE201_POSTGRES_TEST_URL"])
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session = session_factory()
    try:
        tenant_one, allocation_one = _postgres_invoice_bundle(db_session, "owner-a")
        tenant_two, allocation_two = _postgres_invoice_bundle(db_session, "owner-b")
        deployed = dict(
            db_session.execute(
                text(
                    """
                    SELECT conname, pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conname IN (
                        'uq_payment_allocation_id_tenant',
                        'fk_reconciliation_item_allocation_owner',
                        'fk_reconciliation_exception_item_run',
                        'fk_reconciliation_exception_run_scope'
                    )
                    """
                )
            ).all()
        )
        assert set(deployed) == {
            "uq_payment_allocation_id_tenant",
            "fk_reconciliation_item_allocation_owner",
            "fk_reconciliation_exception_item_run",
            "fk_reconciliation_exception_run_scope",
        }
        owner_definition = deployed["fk_reconciliation_item_allocation_owner"]
        assert "(payment_allocation_id, tenant_id)" in owner_definition
        assert "payment_allocations(id, tenant_id)" in owner_definition

        tenant_run = ReconciliationRun(
            scope_type="tenant",
            scope_ref=f"tenant:{tenant_one.id}",
            tenant_id=tenant_one.id,
            provider="mercadopago",
            provider_account_ref=f"merchant:{uuid4()}",
            business_date=datetime.now(timezone.utc).date(),
            source_checksum=uuid4().hex,
            audit_reference=f"audit:{uuid4()}",
        )
        db_session.add(tenant_run)
        db_session.flush()
        tenant_item = ReconciliationItem(
            reconciliation_run_id=tenant_run.id,
            scope_type="tenant",
            scope_ref=f"tenant:{tenant_one.id}",
            tenant_id=tenant_one.id,
            provider="mercadopago",
            source_reference=f"source:{uuid4()}",
            source_fingerprint=uuid4().hex,
            payment_allocation_id=allocation_one.id,
            expected_amount=Decimal("2700.00"),
            observed_amount=Decimal("2700.00"),
            currency="COP",
            status="matched",
            audit_reference=f"audit:{uuid4()}",
            occurred_at=datetime.now(timezone.utc),
        )
        db_session.add(tenant_item)
        db_session.commit()

        tenant_item.payment_allocation_id = allocation_two.id
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        sqlstate = getattr(exc_info.value.orig, "sqlstate", None) or getattr(
            exc_info.value.orig, "pgcode", None
        )
        assert sqlstate == "23503"
        assert "fk_reconciliation_item_allocation_owner" in str(exc_info.value.orig)
        db_session.rollback()

        platform_run = ReconciliationRun(
            scope_type="platform",
            scope_ref="platform:eslatin",
            tenant_id=None,
            provider="mercadopago",
            provider_account_ref=f"merchant:{uuid4()}",
            business_date=datetime.now(timezone.utc).date(),
            source_checksum=uuid4().hex,
            audit_reference=f"audit:{uuid4()}",
        )
        db_session.add(platform_run)
        db_session.flush()
        platform_item = ReconciliationItem(
            reconciliation_run_id=platform_run.id,
            scope_type="platform",
            scope_ref="platform:eslatin",
            tenant_id=None,
            provider="mercadopago",
            source_reference=f"source:{uuid4()}",
            source_fingerprint=uuid4().hex,
            payment_allocation_id=allocation_two.id,
            expected_amount=Decimal("2700.00"),
            observed_amount=Decimal("2700.00"),
            currency="COP",
            status="matched",
            audit_reference=f"audit:{uuid4()}",
            occurred_at=datetime.now(timezone.utc),
        )
        db_session.add(platform_item)
        db_session.commit()

        tenant_exception = ReconciliationException(
            reconciliation_run_id=tenant_run.id,
            reconciliation_item_id=tenant_item.id,
            scope_type="tenant",
            scope_ref=f"tenant:{tenant_one.id}",
            tenant_id=tenant_one.id,
            status="manual_review",
            reason_code="ownership-regression",
            audit_reference=f"audit:{uuid4()}",
        )
        platform_exception = ReconciliationException(
            reconciliation_run_id=platform_run.id,
            reconciliation_item_id=platform_item.id,
            scope_type="platform",
            scope_ref="platform:eslatin",
            tenant_id=None,
            status="manual_review",
            reason_code="platform-regression",
            audit_reference=f"audit:{uuid4()}",
        )
        db_session.add_all([tenant_exception, platform_exception])
        db_session.commit()

        assert tenant_item.payment_allocation_id == allocation_one.id
        assert platform_item.payment_allocation_id == allocation_two.id
    finally:
        db_session.rollback()
        db_session.close()
        engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("BE201_POSTGRES_TEST_URL"),
    reason="BE201_POSTGRES_TEST_URL is required for the PostgreSQL ownership regression",
)
def test_postgresql_support_case_linked_resource_tenant_ownership():
    """Close BE201-QA-003 for every tenant-bound support link and event."""
    engine = create_engine(os.environ["BE201_POSTGRES_TEST_URL"])
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session = session_factory()
    try:
        owner = _postgres_support_resources(db_session, "support-owner")
        foreign = _postgres_support_resources(db_session, "support-foreign")
        expected_constraints = {
            "fk_support_case_invoice_owner",
            "fk_support_case_session_owner",
            "fk_support_case_refund_owner",
            "fk_support_case_chargeback_owner",
            "fk_support_case_rail_owner",
            "fk_support_case_event_owner",
        }
        deployed = dict(
            db_session.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) "
                    "FROM pg_constraint WHERE conname = ANY(:names)"
                ),
                {"names": list(expected_constraints)},
            ).all()
        )
        assert set(deployed) == expected_constraints
        for constraint_name in expected_constraints - {"fk_support_case_event_owner"}:
            assert "tenant_id" in deployed[constraint_name]

        same_tenant = SupportCase(
            tenant_id=owner["tenant"].id,
            app_user_id=owner["user"].id,
            invoice_id=owner["invoice"].id,
            session_id=owner["session"].id,
            refund_case_id=owner["refund_case"].id,
            chargeback_case_id=owner["chargeback_case"].id,
            rail_control_id=owner["tenant_rail"].id,
            category="other",
            audit_reference=f"audit:{uuid4()}",
        )
        null_links = SupportCase(
            tenant_id=owner["tenant"].id,
            app_user_id=owner["user"].id,
            category="other",
            audit_reference=f"audit:{uuid4()}",
        )
        db_session.add_all([same_tenant, null_links])
        db_session.commit()

        cross_tenant_cases = {
            "invoice_id": (
                foreign["invoice"].id,
                "fk_support_case_invoice_owner",
            ),
            "session_id": (
                foreign["session"].id,
                "fk_support_case_session_owner",
            ),
            "refund_case_id": (
                foreign["refund_case"].id,
                "fk_support_case_refund_owner",
            ),
            "chargeback_case_id": (
                foreign["chargeback_case"].id,
                "fk_support_case_chargeback_owner",
            ),
            "rail_control_id": (
                foreign["tenant_rail"].id,
                "fk_support_case_rail_owner",
            ),
        }
        for field_name, (resource_id, constraint_name) in cross_tenant_cases.items():
            wrong_owner = SupportCase(
                tenant_id=owner["tenant"].id,
                app_user_id=owner["user"].id,
                category="other",
                audit_reference=f"audit:{uuid4()}",
                **{field_name: resource_id},
            )
            _assert_postgresql_fk_rejected(
                db_session, wrong_owner, constraint_name
            )

        platform_rail_link = SupportCase(
            tenant_id=owner["tenant"].id,
            app_user_id=owner["user"].id,
            rail_control_id=owner["platform_rail"].id,
            category="other",
            audit_reference=f"audit:{uuid4()}",
        )
        _assert_postgresql_fk_rejected(
            db_session,
            platform_rail_link,
            "fk_support_case_rail_owner",
        )

        same_tenant_event = SupportCaseEvent(
            tenant_id=owner["tenant"].id,
            support_case_id=same_tenant.id,
            event_type="case_opened",
            actor_type="system",
            actor_ref="system:be201-test",
            visibility="internal",
            audit_reference=f"audit:{uuid4()}",
        )
        db_session.add(same_tenant_event)
        db_session.commit()

        cross_tenant_event = SupportCaseEvent(
            tenant_id=foreign["tenant"].id,
            support_case_id=same_tenant.id,
            event_type="case_updated",
            actor_type="system",
            actor_ref="system:be201-test",
            visibility="internal",
            audit_reference=f"audit:{uuid4()}",
        )
        _assert_postgresql_fk_rejected(
            db_session,
            cross_tenant_event,
            "fk_support_case_event_owner",
        )
    finally:
        db_session.rollback()
        db_session.close()
        engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("BE201_POSTGRES_TEST_URL"),
    reason="BE201_POSTGRES_TEST_URL is required for the PostgreSQL migration regression",
)
def test_postgresql_support_dirty_link_migration_fails_atomically():
    """Dirty ownership blocks 012 without rewriting facts or advancing revision."""
    engine = create_engine(os.environ["BE201_POSTGRES_TEST_URL"])
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    setup_session = session_factory()
    try:
        owner = _postgres_support_resources(setup_session, "dirty-owner")
        foreign = _postgres_support_resources(setup_session, "dirty-foreign")
        owner_tenant_id = owner["tenant"].id
        owner_user_id = owner["user"].id
        foreign_resource_ids = {
            "invoice_id": foreign["invoice"].id,
            "session_id": foreign["session"].id,
            "refund_case_id": foreign["refund_case"].id,
            "chargeback_case_id": foreign["chargeback_case"].id,
            "rail_control_id": foreign["tenant_rail"].id,
        }
    finally:
        setup_session.close()

    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "012_pay_mp_002_be201_typed_facts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "be201_support_dirty_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    connection = engine.connect()
    transaction = connection.begin()
    dirty_case_id = uuid4()
    try:
        revision_before = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        support_owner_constraints = {
            "invoice_id": "fk_support_case_invoice_owner",
            "session_id": "fk_support_case_session_owner",
            "refund_case_id": "fk_support_case_refund_owner",
            "chargeback_case_id": "fk_support_case_chargeback_owner",
            "rail_control_id": "fk_support_case_rail_owner",
        }
        for constraint_name in support_owner_constraints.values():
            connection.execute(
                text(
                    f"ALTER TABLE support_cases DROP CONSTRAINT {constraint_name}"
                )
            )
        now = datetime.now(timezone.utc)
        connection.execute(
            text(
                "INSERT INTO support_cases "
                "(id, case_reference, tenant_id, app_user_id, invoice_id, "
                "session_id, refund_case_id, chargeback_case_id, rail_control_id, "
                "category, status, priority, version, schema_version, "
                "audit_reference, created_at, updated_at) "
                "VALUES (:id, :case_reference, :tenant_id, :app_user_id, "
                ":invoice_id, :session_id, :refund_case_id, :chargeback_case_id, "
                ":rail_control_id, 'other', 'open', 'normal', 1, 1, "
                ":audit_reference, :created_at, :updated_at)"
            ),
            {
                "id": dirty_case_id,
                "case_reference": f"support-dirty-{uuid4().hex}",
                "tenant_id": owner_tenant_id,
                "app_user_id": owner_user_id,
                **foreign_resource_ids,
                "audit_reference": f"audit:{uuid4()}",
                "created_at": now,
                "updated_at": now,
            },
        )
        migration.op = Operations(MigrationContext.configure(connection))
        with pytest.raises(RuntimeError) as exc_info:
            migration.upgrade()
        for field_name in support_owner_constraints:
            assert f"{field_name}=1" in str(exc_info.value)

        persisted = connection.execute(
            text(
                "SELECT tenant_id, invoice_id, session_id, refund_case_id, "
                "chargeback_case_id, rail_control_id "
                "FROM support_cases WHERE id = :id"
            ),
            {"id": dirty_case_id},
        ).one()
        assert persisted.tenant_id == owner_tenant_id
        for field_name, resource_id in foreign_resource_ids.items():
            assert getattr(persisted, field_name) == resource_id
        revision_after = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert revision_after == revision_before
        deployed_support_constraints = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'support_cases'::regclass"
                )
            )
        }
        assert not (
            set(support_owner_constraints.values()) & deployed_support_constraints
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
