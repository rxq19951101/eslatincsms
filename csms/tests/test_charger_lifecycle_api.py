"""Charger lifecycle API tests for the migration-free test-phase contract."""

from datetime import datetime, timezone

from app.core.ocpp_auth import hash_ocpp_secret
from app.database.models import AuditLog, ChargePoint, ChargingSession, QrToken
from app.services.asset_lifecycle_service import (
    CHARGER_DELETE_ACTION,
    CHARGER_RESTORE_ACTION,
    CHARGER_RETIRE_ACTION,
)


def test_retirement_preflight_and_retire_block_ongoing_session(
    admin_client,
    db_session,
    sample_charge_point,
    sample_evse,
):
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=101,
        id_tag="TEST-TAG",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
        payment_status="pending",
    )
    sample_charge_point.ocpp_auth_secret_hash = hash_ocpp_secret("old-secret")
    db_session.add(session)
    db_session.commit()

    preflight = admin_client.get(
        f"/api/v1/chargers/{sample_charge_point.id}/retirement-preflight"
    )
    assert preflight.status_code == 200
    assert preflight.json()["can_retire_now"] is False
    assert preflight.json()["counts"]["ongoing_sessions"] == 1

    response = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/retire",
        json={"reason": "Physical charger removed"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "charger_retirement_blocked"
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.is_active is True
    assert sample_charge_point.ocpp_auth_secret_hash == hash_ocpp_secret("old-secret")


def test_retire_is_atomic_and_idempotent(
    admin_client,
    db_session,
    sample_charge_point,
):
    sample_charge_point.commissioning_status = "commissioned"
    sample_charge_point.ocpp_auth_secret_hash = hash_ocpp_secret("old-secret")
    qr_token = QrToken(
        token="lifecycle-test-token",
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        connector_id=1,
    )
    db_session.add(qr_token)
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/retire",
        json={"reason": "  Physical charger removed  "},
    )
    assert response.status_code == 200
    assert response.json()["lifecycle_status"] == "retired"
    assert response.json()["retired_at"] is not None

    db_session.refresh(sample_charge_point)
    db_session.refresh(qr_token)
    assert sample_charge_point.is_active is False
    assert sample_charge_point.commissioning_status == "suspended"
    assert sample_charge_point.ocpp_auth_secret_hash is None
    assert qr_token.revoked_at is not None

    second = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/retire",
        json={"reason": "Physical charger removed again"},
    )
    assert second.status_code == 200
    assert second.json()["retired_at"] == response.json()["retired_at"]
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_charge_point.id),
            AuditLog.action == CHARGER_RETIRE_ACTION,
        )
        .count()
        == 1
    )

    detail = admin_client.get(f"/api/v1/chargers/{sample_charge_point.id}")
    assert detail.status_code == 200
    assert detail.json()["lifecycle_status"] == "retired"
    assert detail.json()["retirement_reason"] == "Physical charger removed"


def test_restore_returns_one_time_new_ocpp_secret(
    admin_client,
    db_session,
    sample_charge_point,
):
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "suspended"
    sample_charge_point.ocpp_auth_secret_hash = None
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/restore",
        json={"reason": "Device returned to service"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["lifecycle_status"] == "active"
    assert data["commissioning_status"] == "testing"
    assert data["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert data["ocpp_secret"]
    assert data["credential_rotated"] is True

    db_session.refresh(sample_charge_point)
    assert sample_charge_point.is_active is True
    assert sample_charge_point.ocpp_auth_secret_hash == hash_ocpp_secret(data["ocpp_secret"])
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_charge_point.id),
            AuditLog.action == CHARGER_RESTORE_ACTION,
        )
        .count()
        == 1
    )

    original_hash = sample_charge_point.ocpp_auth_secret_hash
    repeated = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/restore",
        json={"reason": "Device returned to service"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["ocpp_secret"] is None
    assert repeated.json()["credential_rotated"] is False
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.ocpp_auth_secret_hash == original_hash
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_charge_point.id),
            AuditLog.action == CHARGER_RESTORE_ACTION,
        )
        .count()
        == 1
    )


def test_permanent_delete_only_accepts_unused_draft(
    admin_client,
    db_session,
    sample_site,
):
    charge_point = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-DELETE-UNUSED",
        display_code="D01",
        is_active=True,
        commissioning_status="draft",
    )
    db_session.add(charge_point)
    db_session.commit()
    charge_point_uuid = charge_point.id
    charge_point_id = str(charge_point_uuid)

    mismatch = admin_client.request(
        "DELETE",
        f"/api/v1/chargers/{charge_point_id}",
        json={"confirmation": "WRONG", "reason": "Created by mistake"},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "charger_delete_confirmation_mismatch"

    response = admin_client.request(
        "DELETE",
        f"/api/v1/chargers/{charge_point_id}",
        json={
            "confirmation": "CP-DELETE-UNUSED",
            "reason": "Created by mistake",
        },
    )
    assert response.status_code == 200
    assert db_session.query(ChargePoint).filter(ChargePoint.id == charge_point_uuid).first() is None
    delete_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == charge_point_id,
            AuditLog.action == CHARGER_DELETE_ACTION,
        )
        .one()
    )
    assert delete_audit.audit_metadata["reason"] == "Created by mistake"
