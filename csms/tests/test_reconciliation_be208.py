from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.database.base import tenant_id_context
from app.database.models import AdminUser, ReconciliationException, ReconciliationItem, ReconciliationWorkItem
from app.services.reconciliation import ReconciliationService
from app.services.reconciliation import ReconciliationError


def _admin(db, *, super_admin=True):
    admin = AdminUser(
        username=f"be208-{uuid4().hex[:8]}",
        email=f"be208-{uuid4().hex[:8]}@example.test",
        password_hash="test-only",
        is_super_admin=super_admin,
    )
    db.add(admin)
    db.flush()
    return admin


def _fact(service, db, source_type, *, canonical="invoice-1", amount="100.00", fee="0.00", release="100.00", **kwargs):
    source_reference = kwargs.pop("source_reference", f"{source_type}-{uuid4().hex[:8]}")
    fee = kwargs.pop("fee_amount", fee)
    release = kwargs.pop("release_amount", release)
    source_watermark = kwargs.pop("source_watermark", f"wm-{source_type}")
    return service.ingest_source_fact(
        db,
        source_type=source_type,
        source_reference=source_reference,
        canonical_reference=canonical,
        amount=amount,
        currency="COP",
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        merchant_reference="merchant-test",
        fee_amount=fee,
        release_amount=release,
        source_watermark=source_watermark,
        occurred_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        **kwargs,
    )


def test_be208_three_way_match_and_replay_is_bounded(db_session):
    service = ReconciliationService()
    admin = _admin(db_session)
    run = service.create_run(
        db_session,
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        business_date=date(2026, 8, 14),
        source_checksum="checksum-1",
        run_type="daily",
        actor=admin,
    )
    for source_type in ("eslatin", "provider", "funds"):
        _fact(service, db_session, source_type)

    matched = service.match_run(db_session, run.id, limit=10)
    item = db_session.query(ReconciliationItem).one()
    assert matched.status == "completed"
    assert item.status == "matched"
    assert matched.item_count == 1

    replayed = service.replay_run(db_session, run.id, limit=1)
    assert replayed.status == "completed"
    assert db_session.query(ReconciliationItem).one().replay_count == 1


def test_be208_duplicate_and_conflicting_source_facts_are_distinct(db_session):
    service = ReconciliationService()
    first = _fact(service, db_session, "provider", source_reference="provider-reference-1")
    duplicate = service.ingest_source_fact(
        db_session,
        source_type="provider",
        source_reference="provider-reference-1",
        canonical_reference="invoice-1",
        amount="100.00",
        currency="COP",
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        merchant_reference="merchant-test",
        fee_amount="0.00",
        release_amount="100.00",
        source_watermark="wm-provider",
        occurred_at=first.occurred_at,
    )
    conflict = service.ingest_source_fact(
        db_session,
        source_type="provider",
        source_reference="provider-reference-1",
        canonical_reference="invoice-1",
        amount="101.00",
        currency="COP",
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        merchant_reference="merchant-test",
        occurred_at=first.occurred_at,
    )
    assert duplicate.id == first.id
    assert conflict.id != first.id
    assert conflict.status == "conflict"
    assert conflict.conflict_code == "source_payload_conflict"


def test_be208_fee_exception_requires_two_actors_and_expires_closed_fail_closed(db_session):
    service = ReconciliationService()
    finance = _admin(db_session)
    platform = _admin(db_session)
    run = service.create_run(
        db_session,
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        business_date=date(2026, 8, 14),
        source_checksum="checksum-fee",
        actor=finance,
    )
    _fact(service, db_session, "eslatin", fee="0.00")
    _fact(service, db_session, "provider", fee="1.00")
    _fact(service, db_session, "funds", fee="2.00")
    service.match_run(db_session, run.id, limit=10)
    exception = db_session.query(ReconciliationException).one()
    requested = service.request_temporary_acceptance(
        db_session,
        actor=finance,
        exception_id=exception.id,
        reason="bank fee timing review",
        expected_version=exception.version,
        idempotency_key="fee-request-1",
    )
    approved = service.decide_temporary_acceptance(
        db_session,
        actor=platform,
        exception_id=requested.id,
        decision="approve",
        reason="approved for bounded review",
        expected_version=requested.version,
        idempotency_key="fee-decision-1",
    )
    assert approved.status == "temporarily_accepted"
    accepted_until = approved.temporarily_accepted_until
    if accepted_until.tzinfo is None:
        accepted_until = accepted_until.replace(tzinfo=timezone.utc)
    assert accepted_until <= datetime.now(timezone.utc) + timedelta(hours=24, seconds=1)
    expired = service.expire_temporary_acceptances(
        db_session,
        now=accepted_until + timedelta(seconds=1),
    )
    db_session.refresh(approved)
    assert expired == 1
    assert approved.status == "mismatch"


def test_be208_tenant_scope_and_work_dlq_are_server_bound(db_session):
    service = ReconciliationService()
    admin = _admin(db_session, super_admin=False)
    tenant = uuid4()
    token = tenant_id_context.set(tenant)
    try:
        run = service.create_run(
            db_session,
            provider="mercadopago",
            provider_account_ref="mp-account-test",
            business_date=date(2026, 8, 14),
            source_checksum="checksum-tenant",
            actor=admin,
        )
    finally:
        tenant_id_context.reset(token)
    assert run.scope_type == "tenant"
    assert run.scope_ref == f"tenant:{tenant}"

    _fact(service, db_session, "provider", canonical="tenant-invoice", source_watermark="wm-tenant", scope_type="tenant", scope_ref=f"tenant:{tenant}", tenant_id=tenant)
    work = db_session.query(ReconciliationWorkItem).one()
    claimed = service.claim_work(db_session, worker_id="worker-be208", limit=1)
    assert claimed[0].id == work.id
    for _ in range(work.max_retries):
        work = db_session.query(ReconciliationWorkItem).one()
        work.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.commit()
        service.claim_work(db_session, worker_id="worker-be208", limit=1)
        work = db_session.query(ReconciliationWorkItem).one()
        service.fail_work(db_session, work.id, worker_id="worker-be208", error_code="bounded_test", retry_delay_seconds=1)
    db_session.refresh(work)
    assert work.status == "dead_letter"


def test_be208_rejects_raw_payload_and_unbounded_limits(db_session):
    service = ReconciliationService()
    try:
        service.ingest_source_fact(
            db_session,
            source_type="provider",
            source_reference="provider-raw",
            canonical_reference="invoice-raw",
            amount="1.00",
            currency="COP",
            provider="mercadopago",
            provider_account_ref="mp-account-test",
            payload={"provider": "must-not-persist"},
        )
    except ReconciliationError as exc:
        assert "Raw Provider payload" in str(exc)
    else:
        raise AssertionError("raw provider payload was accepted")

    try:
        service.claim_work(db_session, worker_id="worker-be208", limit=101)
    except ReconciliationError as exc:
        assert "bounds" in str(exc)
    else:
        raise AssertionError("unbounded work claim was accepted")


def test_be208_admin_contract_router_is_registered():
    from app.api.v1.admin.reconciliation import router

    routes = {(route.path, tuple(sorted(route.methods or set()))) for route in router.routes}
    assert ("/runs", ("GET",)) in routes
    assert ("/runs/{run_id}", ("GET",)) in routes
    assert ("/runs/{run_id}/items", ("GET",)) in routes
    assert ("/exceptions", ("GET",)) in routes
    assert ("/exceptions/{exception_id}", ("GET",)) in routes
    assert ("/exceptions/{exception_id}/resolution-intents", ("POST",)) in routes
    assert ("/exceptions/{exception_id}/temporary-acceptance-requests", ("POST",)) in routes
    assert ("/temporary-acceptance-requests/{request_id}/decisions", ("POST",)) in routes
    assert ("/exports", ("POST",)) in routes
    assert ("/exports/{export_id}", ("GET",)) in routes
    assert ("/exports/{export_id}/download", ("GET",)) in routes


def test_be208_export_is_bounded_and_one_time(db_session):
    service = ReconciliationService()
    admin = _admin(db_session)
    run = service.create_run(
        db_session,
        provider="mercadopago",
        provider_account_ref="mp-account-test",
        business_date=date(2026, 8, 14),
        source_checksum="checksum-export",
        actor=admin,
    )
    for source_type in ("eslatin", "provider", "funds"):
        _fact(service, db_session, source_type)
    service.match_run(db_session, run.id, limit=10)
    export = service.create_export(db_session, actor=admin, run_id=run.id, filters={"status": ["matched"]}, idempotency_key="export-1")
    assert export.status == "queued"
    ready = service.generate_export(db_session, actor=admin, export_id=export.id)
    assert ready.status == "ready"
    content = service.download_export(db_session, actor=admin, export_id=export.id)
    assert "canonical_reference" in content
    try:
        service.download_export(db_session, actor=admin, export_id=export.id)
    except Exception as exc:
        assert getattr(exc, "code", None) == "EXPORT_CONSUMED"
        assert getattr(exc, "status_code", None) == 410
    else:
        raise AssertionError("export was downloaded twice")
