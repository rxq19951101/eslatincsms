"""Focused tests for tenant-scoped asset archive queries."""

from datetime import datetime


def test_asset_archive_lists_filters_and_links_lifecycle_history(
    admin_client,
    sample_site,
    sample_charge_point,
):
    retired = admin_client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/retire",
        json={"reason": "Physical charger removed"},
    )
    assert retired.status_code == 200

    archived = admin_client.post(
        f"/api/v1/sites/{sample_site.id}/archive",
        json={"reason": "Location contract ended"},
    )
    assert archived.status_code == 200

    sites_response = admin_client.get("/api/v1/asset-archive/sites")
    assert sites_response.status_code == 200
    sites = sites_response.json()
    assert len(sites) == 1
    assert sites[0]["id"] == str(sample_site.id)
    assert sites[0]["lifecycle_status"] == "archived"
    assert sites[0]["archive_reason"] == "Location contract ended"
    assert sites[0]["retired_charge_points_count"] == 1
    assert sites[0]["archived_by"]["username"] == "test-admin"

    site_reason_search = admin_client.get(
        "/api/v1/asset-archive/sites",
        params={"search": "contract ended"},
    )
    assert [item["id"] for item in site_reason_search.json()] == [str(sample_site.id)]

    chargers_response = admin_client.get("/api/v1/asset-archive/chargers")
    assert chargers_response.status_code == 200
    chargers = chargers_response.json()
    assert len(chargers) == 1
    assert chargers[0]["id"] == str(sample_charge_point.id)
    assert chargers[0]["lifecycle_status"] == "retired"
    assert chargers[0]["retirement_reason"] == "Physical charger removed"
    assert chargers[0]["original_site"]["id"] == str(sample_site.id)
    assert chargers[0]["retired_by"]["username"] == "test-admin"

    charger_search = admin_client.get(
        "/api/v1/asset-archive/chargers",
        params={
            "search": sample_charge_point.ocpp_identity,
            "original_site_id": str(sample_site.id),
        },
    )
    assert [item["id"] for item in charger_search.json()] == [str(sample_charge_point.id)]

    retired_at = datetime.fromisoformat(chargers[0]["retired_at"])
    date_filter = admin_client.get(
        "/api/v1/asset-archive/chargers",
        params={
            "retired_from": retired_at.isoformat(),
            "retired_to": retired_at.isoformat(),
        },
    )
    assert [item["id"] for item in date_filter.json()] == [str(sample_charge_point.id)]


def test_asset_archive_excludes_other_tenants(
    admin_client,
    db_session,
    sample_site,
):
    from app.database.models import AuditLog, ChargePoint, Site, Tenant
    from app.services.asset_lifecycle_service import CHARGER_RETIRE_ACTION, SITE_ARCHIVE_ACTION
    from uuid import uuid4

    other_tenant = Tenant(id=uuid4(), name="Other tenant", status="active")
    other_site = Site(
        tenant_id=other_tenant.id,
        name="Other archived site",
        address="Other tenant address",
        latitude=4.7,
        longitude=-74.2,
        is_active=False,
    )
    db_session.add_all([other_tenant, other_site])
    db_session.flush()
    other_charger = ChargePoint(
        tenant_id=other_tenant.id,
        site_id=other_site.id,
        ocpp_identity="OTHER-TENANT-CP",
        display_code="O01",
        is_active=False,
        commissioning_status="suspended",
    )
    actor_id = db_session.query(AuditLog.actor_id).first()
    fallback_actor_id = actor_id[0] if actor_id else uuid4()
    db_session.add_all([
        other_charger,
        AuditLog(
            tenant_id=other_tenant.id,
            actor_id=fallback_actor_id,
            actor_type="admin",
            action=SITE_ARCHIVE_ACTION,
            resource_type="site",
            resource_id=str(other_site.id),
            audit_metadata={"reason": "Other tenant archive"},
        ),
        AuditLog(
            tenant_id=other_tenant.id,
            actor_id=fallback_actor_id,
            actor_type="admin",
            action=CHARGER_RETIRE_ACTION,
            resource_type="charge_point",
            resource_id=str(other_charger.id),
            audit_metadata={"reason": "Other tenant retirement"},
        ),
    ])
    db_session.commit()

    sites = admin_client.get("/api/v1/asset-archive/sites").json()
    chargers = admin_client.get("/api/v1/asset-archive/chargers").json()
    assert str(other_site.id) not in {item["id"] for item in sites}
    assert str(other_charger.id) not in {item["id"] for item in chargers}
    assert str(sample_site.id) not in {item["id"] for item in sites}
