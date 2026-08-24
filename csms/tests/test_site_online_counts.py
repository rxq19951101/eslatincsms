"""Regression coverage for site-list and site-detail online status consistency."""

from datetime import datetime, timedelta, timezone


def _site_from_list(admin_client, site_id):
    response = admin_client.get("/api/v1/sites?lifecycle_status=active")
    assert response.status_code == 200
    return next(item for item in response.json() if item["id"] == str(site_id))


def _charger_from_site_detail(admin_client, site_id, charge_point_id):
    response = admin_client.get(f"/api/v1/sites/{site_id}")
    assert response.status_code == 200
    return next(
        item
        for item in response.json()["charge_points"]
        if item["id"] == str(charge_point_id)
    )


def test_site_list_does_not_count_a_fresh_offline_status_as_online(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse_status,
):
    now = datetime.now(timezone.utc)
    sample_evse_status.status = "Offline"
    sample_evse_status.last_seen = now
    db_session.commit()

    listed_site = _site_from_list(admin_client, sample_site.id)
    detailed_charger = _charger_from_site_detail(
        admin_client,
        sample_site.id,
        sample_charge_point.id,
    )
    assert listed_site["online_charge_points_count"] == 0
    assert detailed_charger["status"] == "Offline"

    sample_evse_status.status = "Available"
    sample_evse_status.last_seen = now
    db_session.commit()

    listed_site = _site_from_list(admin_client, sample_site.id)
    detailed_charger = _charger_from_site_detail(
        admin_client,
        sample_site.id,
        sample_charge_point.id,
    )
    assert listed_site["online_charge_points_count"] == 1
    assert detailed_charger["status"] == "Available"

    sample_evse_status.last_seen = now - timedelta(minutes=6)
    db_session.commit()

    listed_site = _site_from_list(admin_client, sample_site.id)
    detailed_charger = _charger_from_site_detail(
        admin_client,
        sample_site.id,
        sample_charge_point.id,
    )
    assert listed_site["online_charge_points_count"] == 0
    assert detailed_charger["status"] == "Offline"
