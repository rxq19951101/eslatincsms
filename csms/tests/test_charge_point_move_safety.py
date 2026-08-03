"""Safety constraints for moving charge points between sites."""

import uuid
from datetime import datetime, timezone

from app.database.models import (
    AuditLog,
    ChargePoint,
    ChargingSession,
    EVSE,
    Order,
    OutboxEvent,
    Site,
    Tenant,
)
from app.services.asset_lifecycle_service import CHARGER_MOVE_ACTION


def _target_site(db_session, tenant_id, *, active=True, suffix="target"):
    site = Site(
        tenant_id=tenant_id,
        name=f"Move {suffix} site",
        address=f"Move {suffix} address",
        latitude=4.65,
        longitude=-74.05,
        is_active=active,
    )
    db_session.add(site)
    db_session.commit()
    return site


def _move_request(admin_client, target_site, charge_point, **overrides):
    payload = {
        "charge_point_ids": [str(charge_point.id)],
        "force_move": True,
        "reason": "Physical asset reassigned",
    }
    payload.update(overrides)
    return admin_client.post(
        f"/api/v1/sites/{target_site.id}/bind-charge-points",
        json=payload,
    )


def test_unused_active_charge_point_moves_atomically_and_audits(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    target = _target_site(db_session, sample_site.tenant_id)
    source_id = sample_charge_point.site_id

    response = _move_request(admin_client, target, sample_charge_point)
    assert response.status_code == 200
    assert response.json()["moved"] == [str(sample_charge_point.id)]
    assert response.json()["unchanged"] == []
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.site_id == target.id

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_charge_point.id),
            AuditLog.action == CHARGER_MOVE_ACTION,
        )
        .one()
    )
    assert audit.before_data["site_id"] == str(source_id)
    assert audit.after_data["site_id"] == str(target.id)
    assert audit.audit_metadata["reason"] == "Physical asset reassigned"

    replay = _move_request(admin_client, target, sample_charge_point)
    assert replay.status_code == 200
    assert replay.json()["moved"] == []
    assert replay.json()["unchanged"] == [str(sample_charge_point.id)]
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_charge_point.id),
            AuditLog.action == CHARGER_MOVE_ACTION,
        )
        .count()
        == 1
    )


def test_move_requires_confirmation_and_active_target(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    target = _target_site(db_session, sample_site.tenant_id)
    unconfirmed = _move_request(
        admin_client,
        target,
        sample_charge_point,
        force_move=False,
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["error"]["code"] == "charger_move_blocked"
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.site_id == sample_site.id

    target.is_active = False
    db_session.commit()
    archived = _move_request(admin_client, target, sample_charge_point)
    assert archived.status_code == 409
    assert archived.json()["error"]["code"] == "charger_move_blocked"
    blocker = archived.json()["error"]["details"][0]["blockers"][0]
    assert blocker["type"] == "target_site_archived"
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.site_id == sample_site.id


def test_move_rejects_retired_charger_and_any_session_history(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    target = _target_site(db_session, sample_site.tenant_id)
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "suspended"
    db_session.commit()

    retired = _move_request(admin_client, target, sample_charge_point)
    assert retired.status_code == 409
    retired_blockers = retired.json()["error"]["details"][0]["blockers"]
    assert {item["type"] for item in retired_blockers} == {"charger_not_operational"}

    sample_charge_point.is_active = True
    sample_charge_point.commissioning_status = "commissioned"
    db_session.add(
        ChargingSession(
            tenant_id=sample_charge_point.tenant_id,
            evse_id=sample_evse.id,
            charge_point_id=sample_charge_point.id,
            transaction_id=77201,
            id_tag="MOVE-HISTORY",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            status="completed",
            payment_status="paid",
        )
    )
    db_session.commit()

    history = _move_request(admin_client, target, sample_charge_point)
    assert history.status_code == 409
    history_blockers = history.json()["error"]["details"][0]["blockers"]
    assert "charging_session_history" in {item["type"] for item in history_blockers}
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.site_id == sample_site.id


def test_pending_remote_command_blocks_move_without_partial_update(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    target = _target_site(db_session, sample_site.tenant_id)
    event = OutboxEvent(
        tenant_id=sample_charge_point.tenant_id,
        aggregate_type="ChargePoint",
        aggregate_id=str(sample_charge_point.id),
        event_type="RemoteStartRequested",
        idempotency_key="move-safety-pending-command",
        payload={"charge_point_id": str(sample_charge_point.id)},
        status="pending",
    )
    db_session.add(event)
    db_session.commit()

    response = _move_request(admin_client, target, sample_charge_point)
    assert response.status_code == 409
    blockers = response.json()["error"]["details"][0]["blockers"]
    assert "pending_remote_command" in {item["type"] for item in blockers}
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.site_id == sample_site.id
    assert db_session.query(AuditLog).filter(AuditLog.action == CHARGER_MOVE_ACTION).count() == 0


def test_batch_move_is_atomic_when_one_charger_has_order_history(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    target = _target_site(db_session, sample_site.tenant_id)
    blocked_cp = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-MOVE-ORDER-HISTORY",
        display_code="H01",
        is_active=True,
    )
    db_session.add(blocked_cp)
    db_session.flush()
    db_session.add(
        Order(
            tenant_id=sample_site.tenant_id,
            charge_point_id=blocked_cp.id,
            id_tag="MOVE-ORDER-HISTORY",
            status="completed",
        )
    )
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/sites/{target.id}/bind-charge-points",
        json={
            "charge_point_ids": [
                str(sample_charge_point.id),
                str(blocked_cp.id),
            ],
            "force_move": True,
            "reason": "Atomic move test",
        },
    )
    assert response.status_code == 409
    blockers = response.json()["error"]["details"][0]["blockers"]
    assert "order_history" in {item["type"] for item in blockers}
    db_session.refresh(sample_charge_point)
    db_session.refresh(blocked_cp)
    assert sample_charge_point.site_id == sample_site.id
    assert blocked_cp.site_id == sample_site.id
    assert db_session.query(AuditLog).filter(AuditLog.action == CHARGER_MOVE_ACTION).count() == 0


def test_cross_tenant_charge_point_move_is_forbidden(
    admin_client,
    db_session,
    sample_site,
):
    other_tenant = Tenant(id=uuid.uuid4(), name="Move other tenant", status="active")
    other_site = Site(
        tenant_id=other_tenant.id,
        name="Move other source",
        address="Move other source address",
        latitude=4.7,
        longitude=-74.0,
        is_active=True,
    )
    db_session.add_all([other_tenant, other_site])
    db_session.flush()
    other_cp = ChargePoint(
        tenant_id=other_tenant.id,
        site_id=other_site.id,
        ocpp_identity="CP-MOVE-OTHER-TENANT",
        display_code="O01",
        is_active=True,
    )
    db_session.add(other_cp)
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/bind-charge-points",
        json={
            "charge_point_ids": [str(other_cp.id)],
            "force_move": True,
            "reason": "Invalid cross tenant move",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "charge_point_tenant_mismatch"
    db_session.refresh(other_cp)
    assert other_cp.site_id == other_site.id


def test_archived_site_rejects_new_charge_point_provisioning(
    admin_client,
    db_session,
    sample_site,
):
    sample_site.is_active = False
    db_session.commit()

    nested = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/charge-points",
        json={
            "id": "CP-ARCHIVED-SITE-NESTED",
            "display_code": "N01",
            "connector_count": 1,
        },
    )
    direct = admin_client.post(
        "/api/v1/chargers",
        json={
            "id": "CP-ARCHIVED-SITE-DIRECT",
            "site_id": str(sample_site.id),
        },
    )

    assert nested.status_code == 409
    assert nested.json()["error"]["code"] == "site_not_operational"
    assert direct.status_code == 409
    assert direct.json()["error"]["code"] == "site_not_operational"
    assert db_session.query(ChargePoint).filter(
        ChargePoint.ocpp_identity.in_([
            "CP-ARCHIVED-SITE-NESTED",
            "CP-ARCHIVED-SITE-DIRECT",
        ])
    ).count() == 0
