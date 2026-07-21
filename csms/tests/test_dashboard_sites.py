"""Targeted regression tests for dashboard site summaries."""

from datetime import datetime, timedelta, timezone

from app.database.models import ChargePoint, EVSE, EVSEStatus


def test_dashboard_sites_serializes_uuid_site_id(admin_client, sample_site):
    response = admin_client.get("/api/v1/dashboard/sites")

    assert response.status_code == 200
    assert response.json()[0]["site_id"] == str(sample_site.id)


def test_dashboard_summary_and_sites_share_effective_online_status(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    now = datetime.now(timezone.utc)
    stale_charge_point = ChargePoint(
        ocpp_identity="CP-DASHBOARD-STALE",
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        is_active=True,
    )
    db_session.add(stale_charge_point)
    db_session.flush()
    stale_evse = EVSE(
        tenant_id=sample_site.tenant_id,
        charge_point_id=stale_charge_point.id,
        evse_id=1,
    )
    db_session.add(stale_evse)
    db_session.flush()
    db_session.add_all([
        EVSEStatus(
            tenant_id=sample_site.tenant_id,
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            status="Available",
            last_seen=now - timedelta(minutes=2),
        ),
        EVSEStatus(
            tenant_id=sample_site.tenant_id,
            charge_point_id=stale_charge_point.id,
            evse_id=stale_evse.id,
            status="Charging",
            last_seen=now - timedelta(minutes=10),
        ),
    ])
    db_session.commit()

    summary_response = admin_client.get("/api/v1/dashboard/summary")
    sites_response = admin_client.get("/api/v1/dashboard/sites")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_charge_points"] == 2
    assert summary["online_charge_points"] == 1
    assert summary["offline_charge_points"] == 1
    assert summary["available_charge_points"] == 1
    assert summary["charging_charge_points"] == 0

    assert sites_response.status_code == 200
    site = sites_response.json()[0]
    assert site["charge_points_count"] == 2
    assert site["online_charge_points_count"] == 1
    assert site["available_charge_points"] == 1
    assert site["charging_charge_points"] == 0
