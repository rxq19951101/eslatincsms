import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database.models import (
    AdminUser,
    ChargePoint,
    ChargingSession,
    EVSE,
    Invoice,
    MeterValue,
    PricingSnapshot,
    Site,
    Tariff,
    Tenant,
)


def test_transaction_records_paginate_use_invoice_authority_and_export_same_filter(
    admin_client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    started_at = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    sample_charge_point.display_code = "A01"
    sample_charge_point.display_name = "Lobby charger"
    sample_evse.physical_reference = "A01-1"
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=7201,
        id_tag="=FORMULA",
        start_time=started_at,
        end_time=started_at + timedelta(minutes=30),
        meter_start=1000,
        meter_stop=3500,
        status="completed",
        payment_status="pending",
    )
    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        name="Transaction tariff",
        base_price_per_kwh=Decimal("1000.00"),
        service_fee=Decimal("200.00"),
        valid_from=started_at - timedelta(days=1),
        is_active=True,
    )
    db_session.add_all([session, tariff])
    db_session.flush()
    snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=session.id,
        price_per_kwh=Decimal("1000.00"),
        service_fee=Decimal("200.00"),
        snapshot_time=started_at,
    )
    db_session.add(snapshot)
    db_session.flush()
    db_session.add(Invoice(
        tenant_id=sample_tenant.id,
        session_id=session.id,
        pricing_snapshot_id=snapshot.id,
        energy_kwh=Decimal("2.500"),
        duration_minutes=Decimal("30.00"),
        energy_cost=Decimal("2500.00"),
        service_fee=Decimal("200.00"),
        total_amount=Decimal("2700.00"),
        status="paid",
        issued_at=started_at + timedelta(minutes=30),
    ))
    db_session.commit()

    params = {
        "status": "completed",
        "site_id": sample_site.site_code,
        "started_from": "2026-07-20T00:00:00Z",
        "started_to": "2026-07-20T23:59:59Z",
        "limit": 1,
        "offset": 0,
    }
    response = admin_client.get("/api/v1/transactions", params=params)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    record = body["items"][0]
    assert "ocpp_transaction_id" not in record
    assert record["site"]["site_code"] == sample_site.site_code
    assert record["charger"] == {
        "display_code": "A01",
        "display_name": "Lobby charger",
    }
    assert record["connector"]["id"] == str(sample_evse.id)
    assert record["connector"]["connector_number"] == 1
    assert record["connector"]["physical_reference"] == "A01-1"
    assert "evse_id" not in record["connector"]
    assert record["amount"] == "2700.00"
    assert record["currency"] == "COP"
    assert record["payment_status"] == "paid"

    export_params = dict(params)
    export_params.pop("limit")
    export_params.pop("offset")
    exported = admin_client.get("/api/v1/transactions/export", params=export_params)

    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    csv_text = exported.content.decode("utf-8-sig")
    assert record["record_number"] in csv_text
    assert sample_site.site_code in csv_text
    assert "connector_number" in csv_text.splitlines()[0]
    assert "ocpp_transaction_id" not in csv_text.splitlines()[0]
    assert "ocpp_identity" not in csv_text.splitlines()[0]
    assert "evse_id" not in csv_text.splitlines()[0]
    assert "2700.00" in csv_text
    assert "'=FORMULA" in csv_text


def test_active_sessions_require_transactions_read(admin_client, db_session):
    admin = db_session.query(AdminUser).filter(AdminUser.username == "test-admin").one()
    admin.is_super_admin = False
    db_session.commit()

    response = admin_client.get("/api/v1/transactions/active")

    assert response.status_code == 403


def test_active_sessions_include_operational_mapping_cost_and_tenant_isolation(
    admin_client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    now = datetime.now(timezone.utc)
    sample_charge_point.display_name = "Lobby charger"
    sample_evse.physical_reference = "A01-1"
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=101,
        id_tag="RFID-001",
        user_id="user-42",
        start_time=now - timedelta(minutes=30),
        meter_start=1000,
        status="ongoing",
    )
    db_session.add(session)
    db_session.flush()
    db_session.add_all([
        MeterValue(
            tenant_id=sample_tenant.id,
            session_id=session.id,
            timestamp=now - timedelta(minutes=2),
            value=6000,
            sampled_value=[{"measurand": "Power.Active.Import", "value": "7200"}],
        ),
        Tariff(
            tenant_id=sample_tenant.id,
            site_id=sample_site.id,
            name="Site tariff",
            base_price_per_kwh=Decimal("1000.00"),
            service_fee=Decimal("500.00"),
            valid_from=now - timedelta(days=1),
            is_active=True,
        ),
    ])

    other_tenant = Tenant(id=uuid.uuid4(), name="Other tenant", status="active")
    db_session.add(other_tenant)
    db_session.flush()
    other_site = Site(
        tenant_id=other_tenant.id,
        site_code="site_1234567890abcdef",
        name="Other site",
        address="Other tenant address",
        latitude=4.7,
        longitude=-74.1,
    )
    db_session.add(other_site)
    db_session.flush()
    other_charge_point = ChargePoint(
        tenant_id=other_tenant.id,
        site_id=other_site.id,
        ocpp_identity="OTHER-CP",
        display_code="B01",
    )
    db_session.add(other_charge_point)
    db_session.flush()
    other_evse = EVSE(
        tenant_id=other_tenant.id,
        charge_point_id=other_charge_point.id,
        evse_id=1,
        physical_reference="B01-1",
    )
    db_session.add(other_evse)
    db_session.flush()
    db_session.add(ChargingSession(
        tenant_id=other_tenant.id,
        evse_id=other_evse.id,
        charge_point_id=other_charge_point.id,
        transaction_id=202,
        id_tag="OTHER-RFID",
        start_time=now,
        meter_start=0,
        status="ongoing",
    ))
    db_session.commit()

    response = admin_client.get("/api/v1/transactions/active")

    assert response.status_code == 200
    assert len(response.json()) == 1
    active = response.json()[0]
    assert "transaction_id" not in active
    assert "ocpp_identity" not in active
    assert active["site"] == {
        "id": sample_site.site_code,
        "name": sample_site.name,
        "address": sample_site.address,
    }
    assert active["charger"] == {
        "id": str(sample_charge_point.id),
        "display_code": "A01",
        "display_name": "Lobby charger",
    }
    assert active["connector"] == {
        "id": str(sample_evse.id),
        "connector_number": 1,
        "physical_reference": "A01-1",
    }
    assert active["user_reference"] == "user-42"
    assert active["energy_kwh"] == 5.0
    assert active["power_kw"] == 7.2
    assert active["last_meter_at"] is not None
    assert active["estimated_cost"] == "5500.00"
    assert active["currency"] == "COP"


def test_active_session_has_no_estimate_without_reliable_energy(
    admin_client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        ChargingSession(
            tenant_id=sample_tenant.id,
            evse_id=sample_evse.id,
            charge_point_id=sample_charge_point.id,
            transaction_id=303,
            id_tag="RFID-003",
            start_time=now,
            meter_start=1000,
            status="ongoing",
        ),
        Tariff(
            tenant_id=sample_tenant.id,
            charge_point_id=sample_charge_point.id,
            name="Charger tariff",
            base_price_per_kwh=Decimal("900.00"),
            service_fee=Decimal("0.00"),
            valid_from=now - timedelta(days=1),
            is_active=True,
        ),
    ])
    db_session.commit()

    response = admin_client.get("/api/v1/transactions/active")

    assert response.status_code == 200
    active = response.json()[0]
    assert active["energy_kwh"] is None
    assert active["estimated_cost"] is None
    assert active["currency"] is None


def test_active_sessions_do_not_use_other_charger_tariff_as_site_default(
    admin_client,
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    now = datetime.now(timezone.utc)
    other_charge_point = ChargePoint(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        ocpp_identity="CP-TEST-002",
        display_code="A02",
        is_active=True,
    )
    db_session.add(other_charge_point)
    db_session.flush()
    other_evse = EVSE(
        tenant_id=sample_tenant.id,
        charge_point_id=other_charge_point.id,
        evse_id=1,
        physical_reference="A02-1",
    )
    db_session.add(other_evse)
    db_session.flush()

    charger_session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=401,
        id_tag="RFID-401",
        start_time=now - timedelta(minutes=10),
        meter_start=0,
        status="ongoing",
    )
    other_charger_session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=other_evse.id,
        charge_point_id=other_charge_point.id,
        transaction_id=402,
        id_tag="RFID-402",
        start_time=now - timedelta(minutes=10),
        meter_start=0,
        status="ongoing",
    )
    db_session.add_all([charger_session, other_charger_session])
    db_session.flush()
    db_session.add_all([
        MeterValue(
            tenant_id=sample_tenant.id,
            session_id=charger_session.id,
            timestamp=now,
            value=1000,
        ),
        MeterValue(
            tenant_id=sample_tenant.id,
            session_id=other_charger_session.id,
            timestamp=now,
            value=1000,
        ),
        Tariff(
            tenant_id=sample_tenant.id,
            site_id=sample_site.id,
            name="Site default",
            base_price_per_kwh=Decimal("1000.00"),
            service_fee=Decimal("0.00"),
            valid_from=now - timedelta(days=2),
            is_active=True,
        ),
        Tariff(
            tenant_id=sample_tenant.id,
            site_id=sample_site.id,
            charge_point_id=sample_charge_point.id,
            name="Charger specific",
            base_price_per_kwh=Decimal("2000.00"),
            service_fee=Decimal("0.00"),
            valid_from=now - timedelta(days=1),
            is_active=True,
        ),
    ])
    db_session.commit()

    response = admin_client.get("/api/v1/transactions/active")

    assert response.status_code == 200
    active_by_charger = {
        item["charger"]["display_code"]: item for item in response.json()
    }
    assert active_by_charger["A01"]["estimated_cost"] == "2000.00"
    assert active_by_charger["A02"]["estimated_cost"] == "1000.00"
