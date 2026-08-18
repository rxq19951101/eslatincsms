from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.database.base import tenant_id_context
from app.database.models import AdminUser, AuditLog, Tenant
from app.services.audit_event_service import (
    AuditEventCursorInvalid,
    AuditEventPermissionDenied,
    AuditEventRequestInvalid,
    AuditEventService,
)


def _audit(
    db_session,
    *,
    tenant_id,
    actor_id,
    created_at,
    action="view",
    result="success",
    resource_id="resource-1",
    metadata=None,
):
    event = AuditLog(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="admin",
        action=action,
        resource_type="chargeback_case",
        resource_id=resource_id,
        audit_metadata={"result": result, "reason_code": "manual_review", **(metadata or {})},
        created_at=created_at,
    )
    db_session.add(event)
    return event


def _admin(db_session, *, super_admin, suffix):
    admin = AdminUser(
        id=uuid4(),
        username=f"audit-{suffix}",
        email=f"audit-{suffix}@example.com",
        password_hash="test-hash",
        full_name="Audit Operator",
        is_active=True,
        is_super_admin=super_admin,
    )
    db_session.add(admin)
    db_session.flush()
    return admin


def test_audit_event_projection_is_safe_stable_and_cursor_bound(db_session, sample_tenant):
    admin = _admin(db_session, super_admin=True, suffix="projection")
    base = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    first = _audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=admin.id,
        created_at=base,
        resource_id="case-a",
        metadata={
            "source": "admin",
            "count": 1,
            "nested": {"ok": True},
            "raw_provider_payload": {"payment": "must-not-leak"},
            "rawProviderPayload": {"payment": "must-not-leak"},
            "PAN": "4111111111111111",
            "CVV": "123",
            "Token": "must-not-leak",
            "Secret": "must-not-leak",
            "camelContainer": {
                "providerPayload": {"provider": "must-not-leak"},
                "safeValue": "retained",
            },
            "pan": "4111111111111111",
            "cvv": "123",
            "secret": "hidden",
        },
    )
    second = _audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=admin.id,
        created_at=base - timedelta(seconds=1),
        resource_id="case-b",
    )
    db_session.commit()

    token = tenant_id_context.set(None)
    try:
        page = AuditEventService.list_events(db_session, admin=admin, limit=1)
        assert page["items"][0]["event_id"] == str(first.id)
        assert page["items"][0]["scope"] == {
            "type": "tenant",
            "ref": f"tenant:{sample_tenant.id}",
        }
        assert page["items"][0]["actor"]["display_name"] == "Audit Operator"
        safe_metadata = page["items"][0]["safe_metadata"]
        assert safe_metadata["source"] == "admin"
        assert safe_metadata["count"] == 1
        assert safe_metadata["nested"] == {"ok": True}
        assert safe_metadata["camelContainer"] == {"safeValue": "retained"}
        assert {
            "raw_provider_payload",
            "rawProviderPayload",
            "PAN",
            "CVV",
            "Token",
            "Secret",
            "pan",
            "cvv",
            "secret",
        }.isdisjoint(safe_metadata)
        assert page["page"]["has_more"] is True

        next_page = AuditEventService.list_events(
            db_session,
            admin=admin,
            cursor=page["page"]["next_cursor"],
            limit=1,
        )
        assert [item["event_id"] for item in next_page["items"]] == [str(second.id)]
        assert next_page["page"]["has_more"] is False
    finally:
        tenant_id_context.reset(token)


def test_audit_event_scope_and_permission_are_server_authoritative(db_session, sample_tenant):
    other_tenant = Tenant(id=uuid4(), name="Other tenant", status="active")
    db_session.add(other_tenant)
    admin = _admin(db_session, super_admin=False, suffix="tenant")
    super_admin = _admin(db_session, super_admin=True, suffix="tenant-platform")
    _audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=admin.id,
        created_at=datetime.now(timezone.utc),
        resource_id="visible",
    )
    _audit(
        db_session,
        tenant_id=other_tenant.id,
        actor_id=admin.id,
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        resource_id="hidden",
    )
    db_session.commit()

    token = tenant_id_context.set(sample_tenant.id)
    try:
        scoped = AuditEventService.list_events(db_session, admin=super_admin)
        assert {item["resource"]["id"] for item in scoped["items"]} == {"visible"}
        tenant_id_context.set(None)
        with pytest.raises(AuditEventPermissionDenied):
            AuditEventService.list_events(db_session, admin=admin)
    finally:
        tenant_id_context.reset(token)


def test_audit_event_filters_dates_and_cursor_validation(db_session, sample_tenant):
    admin = _admin(db_session, super_admin=True, suffix="validation")
    db_session.commit()
    token = tenant_id_context.set(sample_tenant.id)
    try:
        with pytest.raises(AuditEventRequestInvalid):
            AuditEventService.list_events(db_session, admin=admin, limit="not-a-number")
        with pytest.raises(AuditEventRequestInvalid):
            AuditEventService.list_events(db_session, admin=admin, actor="not-a-uuid")
        with pytest.raises(AuditEventRequestInvalid):
            AuditEventService.list_events(
                db_session,
                admin=admin,
                from_value="2026-08-17T00:00:00Z",
                to_value="2026-08-16T00:00:00Z",
            )
        with pytest.raises(AuditEventCursorInvalid):
            AuditEventService.list_events(db_session, admin=admin, cursor="not-a-cursor")
    finally:
        tenant_id_context.reset(token)


def test_audit_events_admin_route_returns_frozen_page_and_canonical_pagination_error(
    admin_client, db_session, sample_tenant
):
    admin = db_session.query(AdminUser).filter(AdminUser.is_super_admin.is_(True)).first()
    _audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=admin.id,
        created_at=datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        metadata={"source": "admin", "raw_provider_payload": {"secret": "no"}},
    )
    db_session.commit()

    response = admin_client.get(
        "/api/v1/admin/audit-events?resource_type=chargeback_case&resource_id=resource-1&limit=20",
        headers={"Accept": "application/vnd.eslatin.pay-mp-002.v1+json"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.eslatin.pay-mp-002.v1+json")
    body = response.json()
    assert body["page"] == {"next_cursor": None, "has_more": False}
    assert body["items"][0]["resource"] == {"type": "chargeback_case", "id": "resource-1"}
    assert "raw_provider_payload" not in body["items"][0]["safe_metadata"]

    pagination_error = admin_client.get("/api/v1/admin/audit-events?offset=10")
    assert pagination_error.status_code == 400
    assert pagination_error.json()["error"]["code"] == "PAGINATION_MODE_INVALID"
