"""Direct BE-209 support/RBAC/tenant/security evidence."""

from datetime import datetime, timezone
from uuid import uuid4

from app.database.base import tenant_id_context
from app.database.models import (
    AdminUser,
    AppUser,
    AuditLog,
    ChargingSession,
    OutboxEvent,
    SupportCase,
    SupportCaseEvent,
)
from app.services.support_cases import (
    SupportCaseService,
    SupportIdempotencyConflict,
    SupportNotFound,
    emergency_support_status,
    project_support_case,
)


def _app_user(db, suffix="customer"):
    user = AppUser(
        email=f"{suffix}-{uuid4().hex[:8]}@example.test",
        password_hash="test-only",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


def _admin(db, *, super_admin=True, suffix="operator"):
    admin = AdminUser(
        username=f"{suffix}-{uuid4().hex[:8]}",
        email=f"{suffix}-{uuid4().hex[:8]}@example.test",
        password_hash="test-only",
        is_active=True,
        is_super_admin=super_admin,
    )
    db.add(admin)
    db.flush()
    return admin


def _session(db, sample_tenant, sample_charge_point, sample_evse, app_user):
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=1000 + len(db.query(ChargingSession).all()),
        id_tag="be209-test",
        app_user_id=app_user.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db.add(session)
    db.flush()
    return session


def _case(db, tenant_id, app_user_id, *, status="open"):
    case = SupportCase(
        tenant_id=tenant_id,
        app_user_id=app_user_id,
        category="other",
        status=status,
        first_response_target_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        decision_target_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        audit_reference=f"support-test:{uuid4()}",
    )
    db.add(case)
    db.flush()
    return case


def test_be209_app_context_redacts_sensitive_text_and_queues_safe_outbox(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    user = _app_user(db_session)
    session = _session(db_session, sample_tenant, sample_charge_point, sample_evse, user)
    case = SupportCaseService().create_case(
        db_session,
        app_user=user,
        category="charging_issue",
        resource_type="session",
        resource_id=session.id,
        description="PAN 4111111111111111 CVV=123 card token=secret-value",
    )

    db_session.refresh(case)
    event = db_session.query(SupportCaseEvent).filter(SupportCaseEvent.support_case_id == case.id).one()
    notifications = db_session.query(OutboxEvent).filter(
        OutboxEvent.aggregate_id == str(case.id),
        OutboxEvent.event_type == "support.notification.requested",
    ).all()
    assert case.priority == "urgent"
    assert event.note and "4111111111111111" not in event.note
    assert "secret-value" not in event.note
    assert len(notifications) == 1
    payload = notifications[0].payload
    assert "PAN" not in str(payload)
    assert "CVV" not in str(payload)
    assert "token" not in str(payload).lower()
    assert payload["case_reference"] == case.case_reference
    assert emergency_support_status(case)["availability"] == "published_business_hours_only"


def test_be209_admin_scope_hides_cross_tenant_case_and_events_are_idempotent(db_session, sample_tenant):
    owner = _app_user(db_session, "owner")
    foreign_tenant_id = uuid4()
    case = _case(db_session, sample_tenant.id, owner.id)
    admin = _admin(db_session)

    assert project_support_case(db_session, case)["status"] == "open"
    other_context = tenant_id_context.set(foreign_tenant_id)
    try:
        try:
            SupportCaseService().get_admin_case(
                db_session, admin=_admin(db_session, suffix="tenant-admin"),
                case_id=case.id, tenant_id=foreign_tenant_id,
            )
        except SupportNotFound:
            pass
        else:
            raise AssertionError("cross-tenant support case was visible")
    finally:
        tenant_id_context.reset(other_context)

    first = SupportCaseService().add_admin_event(
        db_session,
        admin=admin,
        case_id=case.id,
        event_type="assign",
        note="Assigned to support",
        visibility="internal",
        expected_version=case.version,
        idempotency_key="event-assign-1",
        tenant_id=None,
    )
    second = SupportCaseService().add_admin_event(
        db_session,
        admin=admin,
        case_id=case.id,
        event_type="assign",
        note="Assigned to support",
        visibility="internal",
        expected_version=1,
        idempotency_key="event-assign-1",
        tenant_id=None,
    )
    assert second.id == first.id
    try:
        SupportCaseService().add_admin_event(
            db_session,
            admin=admin,
            case_id=case.id,
            event_type="assign",
            note="different replay text",
            visibility="internal",
            expected_version=1,
            idempotency_key="event-assign-1",
            tenant_id=None,
        )
    except SupportIdempotencyConflict:
        pass
    else:
        raise AssertionError("idempotency fingerprint conflict was not rejected")
    assert db_session.query(SupportCaseEvent).filter(SupportCaseEvent.support_case_id == case.id).count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.resource_id == str(case.id)).count() == 1


def test_be209_lifecycle_is_support_only_and_requires_version(db_session, sample_tenant):
    user = _app_user(db_session, "lifecycle")
    case = _case(db_session, sample_tenant.id, user.id)
    admin = _admin(db_session, suffix="lifecycle")
    event = SupportCaseService().add_admin_event(
        db_session,
        admin=admin,
        case_id=case.id,
        event_type="resolve",
        note="Resolution intent recorded",
        visibility="user",
        expected_version=case.version,
        idempotency_key="event-resolve-1",
        tenant_id=None,
    )
    db_session.refresh(case)
    assert event.status == "resolved"
    assert case.status == "resolved"
    assert case.version == 2
    assert db_session.query(OutboxEvent).filter(
        OutboxEvent.aggregate_id == str(case.id),
        OutboxEvent.event_type == "support.case.state_changed",
    ).count() == 1
    assert not any(
        event_type in {"invoice.updated", "payment.updated", "financial.eligibility.evaluated", "reconciliation.item.matched"}
        for event_type in [row.event_type for row in db_session.query(OutboxEvent).all()]
    )


def test_be209_frozen_support_routes_are_registered():
    from app.api.v1.admin.support import router as admin_router
    from app.api.v1.app.support import router as app_router

    app_routes = {(route.path, tuple(sorted(route.methods or set()))) for route in app_router.routes}
    admin_routes = {(route.path, tuple(sorted(route.methods or set()))) for route in admin_router.routes}
    assert ("/support-cases", ("GET",)) in app_routes
    assert ("/support-cases", ("POST",)) in app_routes
    assert ("/support-cases/{case_id}", ("GET",)) in app_routes
    assert ("/support-cases", ("GET",)) in admin_routes
    assert ("/support-cases/{case_id}", ("GET",)) in admin_routes
    assert ("/support-cases/{case_id}/events", ("POST",)) in admin_routes
