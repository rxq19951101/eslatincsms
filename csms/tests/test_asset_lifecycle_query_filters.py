"""Read models hide archived sites and retired charge points by default."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database.models import (
    ChargePoint,
    ChargingSession,
    EVSE,
    Invoice,
    Order,
    PricingSnapshot,
    Site,
    Tariff,
)


def _add_archived_assets(db_session, sample_site):
    retired_charge_point = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-RETIRED-FILTER",
        display_code="R01",
        is_active=False,
        commissioning_status="suspended",
    )
    archived_site = Site(
        tenant_id=sample_site.tenant_id,
        name="Archived lifecycle site",
        address="Calle 100 # 10-20, Bogota",
        latitude=4.7,
        longitude=-74.0,
        is_active=False,
    )
    db_session.add_all([retired_charge_point, archived_site])
    db_session.flush()
    archived_site_charge_point = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=archived_site.id,
        ocpp_identity="CP-ACTIVE-UNDER-ARCHIVED-SITE",
        display_code="X01",
        is_active=True,
    )
    db_session.add(archived_site_charge_point)
    db_session.commit()
    return retired_charge_point, archived_site, archived_site_charge_point


def _add_dashboard_activity(
    db_session,
    charge_point,
    sequence,
    energy_kwh,
    total_amount,
    evse=None,
):
    now = datetime.now(timezone.utc)
    if evse is None:
        evse = EVSE(
            tenant_id=charge_point.tenant_id,
            charge_point_id=charge_point.id,
            evse_id=1,
        )
        db_session.add(evse)
        db_session.flush()

    session = ChargingSession(
        tenant_id=charge_point.tenant_id,
        evse_id=evse.id,
        charge_point_id=charge_point.id,
        transaction_id=8000 + sequence,
        id_tag=f"DASHBOARD-{sequence}",
        start_time=now,
        end_time=now,
        meter_start=0,
        meter_stop=int(energy_kwh * 1000),
        status="completed",
    )
    db_session.add(session)
    db_session.flush()

    order = Order(
        tenant_id=charge_point.tenant_id,
        session_id=session.id,
        charge_point_id=charge_point.id,
        id_tag=f"DASHBOARD-{sequence}",
        created_at=now,
        status="completed",
    )
    db_session.add(order)
    db_session.flush()

    tariff = Tariff(
        tenant_id=charge_point.tenant_id,
        charge_point_id=charge_point.id,
        name=f"Dashboard tariff {sequence}",
        base_price_per_kwh=Decimal("1.00"),
        service_fee=Decimal("0.00"),
        valid_from=now - timedelta(days=1),
        is_active=True,
    )
    db_session.add(tariff)
    db_session.flush()

    snapshot = PricingSnapshot(
        tenant_id=charge_point.tenant_id,
        tariff_id=tariff.id,
        session_id=session.id,
        order_id=order.id,
        price_per_kwh=Decimal("1.00"),
        service_fee=Decimal("0.00"),
        snapshot_time=now,
    )
    db_session.add(snapshot)
    db_session.flush()

    db_session.add(
        Invoice(
            tenant_id=charge_point.tenant_id,
            session_id=session.id,
            order_id=order.id,
            pricing_snapshot_id=snapshot.id,
            energy_kwh=energy_kwh,
            duration_minutes=Decimal("10.00"),
            energy_cost=total_amount,
            service_fee=Decimal("0.00"),
            total_amount=total_amount,
            status="paid",
            issued_at=now,
        )
    )


def test_admin_site_and_charger_reads_hide_archived_assets(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    retired, archived_site, archived_site_charge_point = _add_archived_assets(
        db_session,
        sample_site,
    )

    sites_response = admin_client.get("/api/v1/sites")
    assert sites_response.status_code == 200
    sites = sites_response.json()
    site_ids = {item["id"] for item in sites}
    assert str(sample_site.id) in site_ids
    assert str(archived_site.id) not in site_ids
    active_site = next(item for item in sites if item["id"] == str(sample_site.id))
    assert active_site["charge_points_count"] == 1

    inclusive_response = admin_client.get("/api/v1/sites?include_inactive=true")
    assert inclusive_response.status_code == 200
    assert str(archived_site.id) in {item["id"] for item in inclusive_response.json()}

    detail_response = admin_client.get(f"/api/v1/sites/{sample_site.id}")
    assert detail_response.status_code == 200
    detail_ids = {item["id"] for item in detail_response.json()["charge_points"]}
    assert str(sample_charge_point.id) in detail_ids
    assert str(retired.id) not in detail_ids

    chargers_response = admin_client.get("/api/v1/chargers")
    assert chargers_response.status_code == 200
    charger_ids = {item["id"] for item in chargers_response.json()}
    assert str(sample_charge_point.id) in charger_ids
    assert str(retired.id) not in charger_ids
    assert str(archived_site_charge_point.id) not in charger_ids


def test_dashboard_counts_only_active_assets(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
):
    _retired, archived_site, _archived_site_charge_point = _add_archived_assets(
        db_session,
        sample_site,
    )

    summary_response = admin_client.get("/api/v1/dashboard/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_sites"] == 1
    assert summary["total_charge_points"] == 1

    sites_response = admin_client.get("/api/v1/dashboard/sites")
    assert sites_response.status_code == 200
    sites = sites_response.json()
    assert {item["site_id"] for item in sites} == {str(sample_site.id)}
    assert sites[0]["charge_points_count"] == 1
    assert str(archived_site.id) not in {item["site_id"] for item in sites}


def test_dashboard_business_metrics_only_include_operational_assets(
    admin_client,
    db_session,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    retired, _archived_site, archived_site_charge_point = _add_archived_assets(
        db_session,
        sample_site,
    )
    _add_dashboard_activity(
        db_session,
        sample_charge_point,
        sequence=1,
        energy_kwh=Decimal("1.000"),
        total_amount=Decimal("10.00"),
        evse=sample_evse,
    )
    _add_dashboard_activity(
        db_session,
        retired,
        sequence=2,
        energy_kwh=Decimal("2.000"),
        total_amount=Decimal("20.00"),
    )
    _add_dashboard_activity(
        db_session,
        archived_site_charge_point,
        sequence=3,
        energy_kwh=Decimal("3.000"),
        total_amount=Decimal("30.00"),
    )
    db_session.commit()

    summary_response = admin_client.get("/api/v1/dashboard/summary")
    trends_response = admin_client.get("/api/v1/dashboard/trends?days=7")
    sites_response = admin_client.get("/api/v1/dashboard/sites?days=7")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["today_orders"] == 1
    assert summary["today_energy_kwh"] == 1.0
    assert float(summary["today_revenue"]) == 10.0

    assert trends_response.status_code == 200
    trends = trends_response.json()
    assert sum(point["value"] for point in trends["orders_trend"]) == 1.0
    assert sum(point["value"] for point in trends["energy_trend"]) == 1.0
    assert sum(point["value"] for point in trends["revenue_trend"]) == 10.0

    assert sites_response.status_code == 200
    sites = sites_response.json()
    assert len(sites) == 1
    assert sites[0]["site_id"] == str(sample_site.id)
    assert sites[0]["orders_count"] == 1
    assert sites[0]["energy_kwh"] == 1.0
    assert float(sites[0]["revenue"]) == 10.0


def test_bindable_candidates_hide_retired_and_archived_assets(
    admin_client,
    db_session,
    sample_site,
):
    active_auto_site = Site(
        tenant_id=sample_site.tenant_id,
        name="站点-CP-BINDABLE-ACTIVE",
        address="Carrera 10 # 20-30, Bogota",
        latitude=4.62,
        longitude=-74.07,
        is_active=True,
    )
    retired_auto_site = Site(
        tenant_id=sample_site.tenant_id,
        name="站点-CP-BINDABLE-RETIRED",
        address="Carrera 11 # 20-30, Bogota",
        latitude=4.63,
        longitude=-74.06,
        is_active=True,
    )
    archived_auto_site = Site(
        tenant_id=sample_site.tenant_id,
        name="站点-CP-BINDABLE-ARCHIVED",
        address="Carrera 12 # 20-30, Bogota",
        latitude=4.64,
        longitude=-74.05,
        is_active=False,
    )
    db_session.add_all([active_auto_site, retired_auto_site, archived_auto_site])
    db_session.flush()
    active = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=active_auto_site.id,
        ocpp_identity="CP-BINDABLE-ACTIVE",
        display_code="B01",
        is_active=True,
    )
    retired = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=retired_auto_site.id,
        ocpp_identity="CP-BINDABLE-RETIRED",
        display_code="B02",
        is_active=False,
        commissioning_status="suspended",
    )
    archived = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=archived_auto_site.id,
        ocpp_identity="CP-BINDABLE-ARCHIVED",
        display_code="B03",
        is_active=True,
    )
    db_session.add_all([active, retired, archived])
    db_session.commit()

    response = admin_client.get(
        f"/api/v1/sites/{sample_site.id}/bindable-charge-points"
    )
    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.json()}
    assert str(active.id) in returned_ids
    assert str(retired.id) not in returned_ids
    assert str(archived.id) not in returned_ids
