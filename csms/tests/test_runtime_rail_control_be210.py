"""Direct BE-210 runtime rail control evidence."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.database.models import AdminUser, AuditLog, OutboxEvent, RuntimeRailControl
from app.services.financial_eligibility import ChargingAdmissionPreflight
from app.services.runtime_rail_control import (
    RailApprovalConflict,
    RailClosed,
    RailIdempotencyConflict,
    RailPermissionDenied,
    RailStateUnknown,
    RuntimeRailControlService,
)


def _admin(db, *, super_admin=True, name="operator"):
    admin = AdminUser(
        id=uuid4(),
        username=f"{name}-{uuid4().hex[:8]}",
        email=f"{name}-{uuid4().hex[:8]}@example.test",
        password_hash="test-only",
        is_active=True,
        is_super_admin=super_admin,
    )
    db.add(admin)
    db.flush()
    return admin


def test_be210_close_reopen_requires_different_actor_and_passed_health(
    db_session, sample_tenant
):
    closer = _admin(db_session, name="closer")
    approver = _admin(db_session, name="approver")

    control = RuntimeRailControlService.close(
        db_session,
        admin=closer,
        axis="payment_creation",
        scope_type="platform",
        scope_ref="platform:eslatin",
        reason="Provider incident",
        incident_reference="INC-BE210-1",
        expected_version=0,
        idempotency_key="close-1",
    )
    assert control.status == "closed"
    assert control.version == 1
    assert db_session.query(AuditLog).filter(AuditLog.resource_id == str(control.id)).count() == 1
    assert db_session.query(OutboxEvent).filter(OutboxEvent.event_type == "rail.control.closed").count() == 1

    replay = RuntimeRailControlService.close(
        db_session,
        admin=closer,
        axis="payment_creation",
        scope_type="platform",
        scope_ref="platform:eslatin",
        reason="Provider incident",
        incident_reference="INC-BE210-1",
        expected_version=0,
        idempotency_key="close-1",
    )
    assert replay.id == control.id
    assert replay.version == 1
    with pytest.raises(RailIdempotencyConflict):
        RuntimeRailControlService.close(
            db_session,
            admin=closer,
            axis="payment_creation",
            scope_type="platform",
            scope_ref="platform:eslatin",
            reason="Different incident",
            incident_reference="INC-BE210-1",
            expected_version=0,
            idempotency_key="close-1",
        )

    request = RuntimeRailControlService.request_reopen(
        db_session,
        admin=closer,
        control_id=control.id,
        reason="Incident mitigated",
        health_check_reference="health-unknown-1",
        expected_version=1,
        idempotency_key="reopen-1",
    )
    assert request.status == "requested"
    with pytest.raises(RailApprovalConflict):
        RuntimeRailControlService.decide_reopen(
            db_session,
            admin=closer,
            request_id=request.id,
            decision="approve",
            reason="same actor must fail",
            expected_version=request.version,
            idempotency_key="decision-same-actor",
        )
    with pytest.raises(RailStateUnknown):
        RuntimeRailControlService.decide_reopen(
            db_session,
            admin=approver,
            request_id=request.id,
            decision="approve",
            reason="health is not known",
            expected_version=request.version,
            idempotency_key="decision-unknown",
        )
    db_session.refresh(control)
    assert control.status == "closed"

    RuntimeRailControlService.record_health_check(
        db_session,
        reference="health-unknown-1",
        axis="payment_creation",
        scope_type="platform",
        scope_ref="platform:eslatin",
        status="passed",
        safe_metadata={"check": "provider-query"},
    )
    approved = RuntimeRailControlService.decide_reopen(
        db_session,
        admin=approver,
        request_id=request.id,
        decision="approve",
        reason="health passed",
        expected_version=request.version,
        idempotency_key="decision-approve-1",
    )
    assert approved.status == "approved"
    db_session.refresh(control)
    assert control.status == "open"
    assert control.reopened_by_admin_id == approver.id
    assert RuntimeRailControlService.payment_creation_decision(
        db_session, provider="mercadopago", tenant_id=sample_tenant.id
    ).status == "open"


def test_be210_overlap_fail_closed_and_financial_eligibility_stays_separate(
    db_session, sample_tenant, sample_site
):
    admin = _admin(db_session, name="platform")
    RuntimeRailControlService.close(
        db_session,
        admin=admin,
        axis="paid_admission",
        scope_type="platform",
        scope_ref="platform:eslatin",
        reason="Admission incident",
        incident_reference="INC-BE210-2",
        expected_version=0,
        idempotency_key="close-admission-platform",
    )
    decision = RuntimeRailControlService.evaluate(
        db_session,
        axis="paid_admission",
        provider="mercadopago",
        tenant_id=sample_tenant.id,
    )
    assert decision.status == "closed"
    assert decision.matched_scope_refs == ("platform:eslatin",)
    with pytest.raises(RailClosed):
        RuntimeRailControlService.require_open(
            db_session,
            axis="paid_admission",
            provider="mercadopago",
            tenant_id=sample_tenant.id,
        )

    rail = ChargingAdmissionPreflight._rail(
        db_session,
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        provider="mercadopago",
        evaluated_at=datetime.now(timezone.utc),
    )
    assert rail.status == "closed"


def test_be210_unknown_overlap_fails_closed_and_tenant_cannot_control_platform(
    db_session, sample_tenant
):
    tenant_admin = _admin(db_session, super_admin=False, name="tenant")
    with pytest.raises(RailPermissionDenied):
        RuntimeRailControlService.close(
            db_session,
            admin=tenant_admin,
            axis="payment_creation",
            scope_type="platform",
            scope_ref="platform:eslatin",
            reason="must be denied",
            incident_reference="INC-BE210-3",
            expected_version=0,
            idempotency_key="tenant-platform-close",
        )

    platform_admin = _admin(db_session, name="platform-unknown")
    control = RuntimeRailControlService.close(
        db_session,
        admin=platform_admin,
        axis="payment_creation",
        scope_type="provider",
        scope_ref="provider:mercadopago",
        reason="unknown health test",
        incident_reference="INC-BE210-4",
        expected_version=0,
        idempotency_key="provider-close",
    )
    db_session.query(RuntimeRailControl).filter(RuntimeRailControl.id == control.id).update({"status": "unknown"})
    db_session.commit()
    decision = RuntimeRailControlService.payment_creation_decision(
        db_session, provider="mercadopago", tenant_id=sample_tenant.id
    )
    assert decision.status == "unknown"
