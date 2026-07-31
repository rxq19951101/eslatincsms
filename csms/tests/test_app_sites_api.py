"""Contract tests for the App's site-oriented public discovery API."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from app.core.auth import create_access_token, get_password_hash
from app.database.models import AppUser, ChargePoint, EVSE, EVSEStatus, Site, Tenant
from app.api.v1.app.sites import _status_counts


def _app_headers(db_session, email: str = "site-discovery@example.test") -> dict[str, str]:
    user = AppUser(
        email=email,
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=Decimal("0.00"),
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token({
        "user_id": str(user.id),
        "user_type": "app_user",
        "aud": "app",
    })
    return {"Authorization": f"Bearer {token}"}


def _add_connector(db_session, charge_point, number: int, status: str, *, stale: bool = False):
    evse = EVSE(
        tenant_id=charge_point.tenant_id,
        charge_point_id=charge_point.id,
        evse_id=number,
        connector_type="Type2" if number == 1 else "CCS2",
        max_power_kw=7.0 if number == 1 else 120.0,
        physical_reference=f"{charge_point.display_code}-{number}",
    )
    db_session.add(evse)
    db_session.flush()
    db_session.add(EVSEStatus(
        tenant_id=charge_point.tenant_id,
        evse_id=evse.id,
        charge_point_id=charge_point.id,
        status=status,
        last_seen=datetime.now(timezone.utc) - (timedelta(minutes=6) if stale else timedelta(seconds=5)),
    ))
    return evse


def test_app_sites_aggregate_charge_points_without_duplicates(
    client,
    db_session,
    sample_site,
    sample_charge_point,
):
    second = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-TEST-002",
        display_code="B02",
        display_name="Fast charger",
        location_hint="North entrance",
        is_active=True,
    )
    db_session.add(second)
    db_session.flush()
    legacy_connector = _add_connector(db_session, sample_charge_point, 1, "Available")
    legacy_connector.physical_reference = " "
    _add_connector(db_session, second, 1, "Charging")
    _add_connector(db_session, second, 2, "Available", stale=True)
    db_session.commit()

    response = client.get("/api/v1/app/sites", headers=_app_headers(db_session))

    assert response.status_code == 200
    matching = [item for item in response.json() if item["id"] == str(sample_site.id)]
    assert len(matching) == 1
    site = matching[0]
    assert site["charger_count"] == 2
    assert site["total_connectors"] == 3
    assert site["available_connectors"] == 1
    assert site["status"] == "Charging"
    assert site["status_counts"] == {
        "available": 1,
        "charging": 1,
        "offline": 1,
        "faulted": 0,
        "occupied": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    assert sum(site["status_counts"].values()) == site["total_connectors"]
    assert site["connector_types"] == ["CCS2", "Type2"]
    assert site["max_power_kw"] == 120.0
    assert site["charging_options"] == [
        {
            "standard": "CCS_2",
            "current_type": "DC",
            "max_power_kw": 120.0,
            "available": 0,
            "total": 1,
            "status_counts": {
                "available": 0,
                "charging": 0,
                "offline": 1,
                "faulted": 0,
                "occupied": 0,
                "unavailable": 0,
                "unknown": 0,
            },
        },
        {
            "standard": "TYPE_2",
            "current_type": "AC",
            "max_power_kw": 7.0,
            "available": 1,
            "total": 2,
            "status_counts": {
                "available": 1,
                "charging": 1,
                "offline": 0,
                "faulted": 0,
                "occupied": 0,
                "unavailable": 0,
                "unknown": 0,
            },
        },
    ]

    detail = client.get(f"/api/v1/app/sites/{sample_site.id}", headers=_app_headers(
        db_session,
        "site-detail@example.test",
    ))
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["charge_points"]) == 2
    assert sum(len(point["connectors"]) for point in body["charge_points"]) == 3
    assert body["charging_options"] == site["charging_options"]
    assert all("ocpp_identity" not in point for point in body["charge_points"])
    assert sample_charge_point.ocpp_identity not in detail.text
    assert second.ocpp_identity not in detail.text
    assert body["charge_points"][0]["display_code"] == "A01"
    legacy_connector_payload = body["charge_points"][0]["connectors"][0]
    assert legacy_connector_payload["connector_number"] == 1
    assert legacy_connector_payload["physical_reference"] is None
    assert "connector_id" not in legacy_connector_payload
    assert "evse_id" not in legacy_connector_payload
    assert body["charge_points"][1]["display_code"] == "B02"
    assert body["charge_points"][1]["display_name"] == "Fast charger"
    assert body["charge_points"][1]["location_hint"] == "North entrance"
    labeled_connector = body["charge_points"][1]["connectors"][0]
    assert labeled_connector["connector_number"] == 1
    assert labeled_connector["physical_reference"] == "B02-1"
    assert "connector_id" not in labeled_connector
    assert "evse_id" not in labeled_connector


def test_status_counts_maps_public_status_groups():
    counts = _status_counts([
        "Available",
        "Charging",
        "Offline",
        "Faulted",
        "Preparing",
        "Finishing",
        "Reserved",
        "SuspendedEV",
        "SuspendedEVSE",
        "Unavailable",
        "UnexpectedStatus",
    ])

    assert counts == {
        "available": 1,
        "charging": 1,
        "offline": 1,
        "faulted": 1,
        "occupied": 5,
        "unavailable": 1,
        "unknown": 1,
    }
    assert sum(counts.values()) == 11


def test_app_sites_charging_option_counts_charging_and_offline(
    client,
    db_session,
    sample_site,
    sample_charge_point,
):
    second = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-MIXED-STATUS-002",
        is_active=True,
    )
    db_session.add(second)
    db_session.flush()
    _add_connector(db_session, sample_charge_point, 1, "Charging")
    _add_connector(db_session, second, 1, "Available", stale=True)
    db_session.commit()

    response = client.get(
        f"/api/v1/app/sites/{sample_site.id}",
        headers=_app_headers(db_session, "mixed-status@example.test"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status_counts"] == {
        "available": 0,
        "charging": 1,
        "offline": 1,
        "faulted": 0,
        "occupied": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    option = body["charging_options"][0]
    assert option["standard"] == "TYPE_2"
    assert option["available"] == 0
    assert option["total"] == 2
    assert option["status_counts"] == body["status_counts"]
    assert sum(option["status_counts"].values()) == option["total"]


def test_app_sites_are_cross_tenant_and_require_app_auth(
    client,
    db_session,
    sample_site,
    sample_charge_point,
):
    other_tenant = Tenant(name="Other public tenant", status="active")
    db_session.add(other_tenant)
    db_session.flush()
    other_site = Site(
        tenant_id=other_tenant.id,
        name="Other public site",
        address="Carrera 7 # 71-21",
        latitude=4.65,
        longitude=-74.06,
        is_active=True,
    )
    db_session.add(other_site)
    db_session.flush()
    db_session.add(ChargePoint(
        tenant_id=other_tenant.id,
        site_id=other_site.id,
        ocpp_identity="CP-OTHER-PUBLIC",
        is_active=True,
    ))
    db_session.commit()

    assert client.get("/api/v1/app/sites").status_code == 401

    headers = _app_headers(db_session, "cross-tenant-sites@example.test")
    headers["X-Tenant-Id"] = str(sample_site.tenant_id)
    response = client.get("/api/v1/app/sites", headers=headers)
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert str(sample_site.id) in ids
    assert str(other_site.id) in ids

    missing = client.get(f"/api/v1/app/sites/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


def test_app_sites_distance_filter_and_limit(
    client,
    db_session,
    sample_site,
):
    response = client.get(
        "/api/v1/app/sites",
        params={
            "latitude": sample_site.latitude,
            "longitude": sample_site.longitude,
            "radius": 100,
            "limit": 1,
        },
        headers=_app_headers(db_session, "nearby-sites@example.test"),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == str(sample_site.id)
    assert response.json()[0]["distance_km"] == 0.0
