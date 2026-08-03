"""Site lifecycle API tests for the migration-free test-phase contract."""

from datetime import datetime, timezone

from app.database.models import AuditLog, ChargingSession, Site
from app.services.asset_lifecycle_service import (
    SITE_ARCHIVE_ACTION,
    SITE_DELETE_ACTION,
    SITE_RESTORE_ACTION,
)


def test_archive_preflight_and_archive_reject_active_charge_point(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    preflight = admin_client.get(
        f"/api/v1/sites/{sample_site.id}/archive-preflight"
    )
    assert preflight.status_code == 200
    assert preflight.json()["can_archive_now"] is False
    assert preflight.json()["counts"]["active_charge_points"] == 1
    assert preflight.json()["blockers"][0]["type"] == "active_charge_point"

    response = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/archive",
        json={"reason": "Location contract ended"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_archive_blocked"
    db_session.refresh(sample_site)
    assert sample_site.is_active is True


def test_retired_charge_point_does_not_block_archive_and_restore_is_idempotent(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "suspended"
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/archive",
        json={"reason": "  Location contract ended  "},
    )
    assert response.status_code == 200
    archived = response.json()
    assert archived["lifecycle_status"] == "archived"
    assert archived["archived_at"] is not None

    second_archive = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/archive",
        json={"reason": "Idempotent archive retry"},
    )
    assert second_archive.status_code == 200
    assert second_archive.json()["archived_at"] == archived["archived_at"]
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_site.id),
            AuditLog.action == SITE_ARCHIVE_ACTION,
        )
        .count()
        == 1
    )

    default_list = admin_client.get("/api/v1/sites")
    assert str(sample_site.id) not in {item["id"] for item in default_list.json()}
    archived_list = admin_client.get("/api/v1/sites?lifecycle_status=archived")
    item = next(row for row in archived_list.json() if row["id"] == str(sample_site.id))
    assert item["archive_reason"] == "Location contract ended"
    assert item["retired_charge_points_count"] == 1
    assert item["active_charge_points_count"] == 0

    detail = admin_client.get(f"/api/v1/sites/{sample_site.id}")
    assert detail.status_code == 200
    assert detail.json()["lifecycle_status"] == "archived"
    assert detail.json()["charge_points"] == []
    assert detail.json()["retired_charge_points_count"] == 1

    restored = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/restore",
        json={"reason": "Location reopened"},
    )
    assert restored.status_code == 200
    assert restored.json()["lifecycle_status"] == "active"
    db_session.refresh(sample_charge_point)
    assert sample_charge_point.is_active is False

    replay = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/restore",
        json={"reason": "Idempotent restore retry"},
    )
    assert replay.status_code == 200
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == str(sample_site.id),
            AuditLog.action == SITE_RESTORE_ACTION,
        )
        .count()
        == 1
    )


def test_retired_charger_with_ongoing_session_still_blocks_site_archive(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "suspended"
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88101,
        id_tag="ARCHIVE-BLOCKER",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
        payment_status="pending",
    )
    db_session.add(session)
    db_session.commit()

    response = admin_client.get(
        f"/api/v1/sites/{sample_site.id}/archive-preflight"
    )
    assert response.status_code == 200
    assert response.json()["counts"]["active_charge_points"] == 0
    assert response.json()["counts"]["retired_charge_points"] == 1
    assert response.json()["counts"]["ongoing_sessions"] == 1
    assert response.json()["can_archive_now"] is False


def test_permanent_delete_only_accepts_completely_unused_site(
    admin_client,
    db_session,
    sample_tenant,
):
    site = Site(
        tenant_id=sample_tenant.id,
        name="Unused delete site",
        address="Unused site address",
        latitude=4.61,
        longitude=-74.11,
        is_active=True,
    )
    db_session.add(site)
    db_session.commit()
    site_uuid = site.id
    site_id = str(site_uuid)
    site_code = site.site_code

    mismatch = admin_client.request(
        "DELETE",
        f"/api/v1/sites/{site_id}",
        json={"confirmation": "wrong-site", "reason": "Created by mistake"},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "site_delete_confirmation_mismatch"

    response = admin_client.request(
        "DELETE",
        f"/api/v1/sites/{site_id}",
        json={"confirmation": site_code, "reason": "Created by mistake"},
    )
    assert response.status_code == 200
    assert db_session.query(Site).filter(Site.id == site_uuid).first() is None
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == site_id,
            AuditLog.action == SITE_DELETE_ACTION,
        )
        .one()
    )
    assert audit.audit_metadata["reason"] == "Created by mistake"


def test_permanent_delete_and_direct_update_reject_used_site(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    update = admin_client.put(
        f"/api/v1/sites/{sample_site.id}",
        json={"is_active": False},
    )
    assert update.status_code == 422
    assert update.json()["error"]["code"] == "site_lifecycle_endpoint_required"

    response = admin_client.request(
        "DELETE",
        f"/api/v1/sites/{sample_site.id}",
        json={
            "confirmation": sample_site.site_code,
            "reason": "Created by mistake",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_permanent_delete_blocked"
    blocker_types = {item["type"] for item in response.json()["error"]["details"][0]["blockers"]}
    assert "charge_point" in blocker_types
