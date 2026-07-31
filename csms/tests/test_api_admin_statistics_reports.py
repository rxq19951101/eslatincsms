from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.database.models import (
    ChargingSession,
    Invoice,
    Order,
    PricingSnapshot,
    Tariff,
)
from app.services.report_service import ReportService


def test_report_service_applies_paid_valid_site_scoped_business_rules(
    db_session,
    sample_tenant,
    sample_site,
    sample_charge_point,
    sample_evse,
):
    report_day = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    range_start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    range_end = datetime(2026, 7, 21, tzinfo=timezone.utc)

    valid_session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=7101,
        id_tag="REPORT-VALID",
        start_time=report_day,
        end_time=report_day,
        meter_start=1000,
        meter_stop=3500,
        status="completed",
    )
    invalid_meter_session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=7102,
        id_tag="REPORT-INVALID-METER",
        start_time=report_day,
        end_time=report_day,
        meter_start=5000,
        meter_stop=4000,
        status="completed",
    )
    end_boundary_session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=7103,
        id_tag="REPORT-END-BOUNDARY",
        start_time=range_end,
        end_time=range_end,
        meter_start=0,
        meter_stop=9000,
        status="completed",
    )
    db_session.add_all([valid_session, invalid_meter_session, end_boundary_session])
    db_session.flush()

    completed_order = Order(
        tenant_id=sample_tenant.id,
        session_id=valid_session.id,
        charge_point_id=sample_charge_point.id,
        user_id="report-user",
        id_tag="REPORT-VALID",
        created_at=report_day,
        status="completed",
    )
    pending_order = Order(
        tenant_id=sample_tenant.id,
        session_id=invalid_meter_session.id,
        charge_point_id=sample_charge_point.id,
        user_id="report-user",
        id_tag="REPORT-PENDING",
        created_at=report_day,
        status="pending",
    )
    db_session.add_all([completed_order, pending_order])
    db_session.flush()

    tariff = Tariff(
        tenant_id=sample_tenant.id,
        site_id=sample_site.id,
        name="Report tariff",
        base_price_per_kwh=Decimal("1000.00"),
        service_fee=Decimal("200.00"),
        valid_from=range_start,
        is_active=True,
    )
    db_session.add(tariff)
    db_session.flush()
    paid_snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=valid_session.id,
        order_id=completed_order.id,
        price_per_kwh=Decimal("1000.00"),
        service_fee=Decimal("200.00"),
        snapshot_time=report_day,
    )
    pending_snapshot = PricingSnapshot(
        tenant_id=sample_tenant.id,
        tariff_id=tariff.id,
        session_id=invalid_meter_session.id,
        order_id=pending_order.id,
        price_per_kwh=Decimal("1000.00"),
        service_fee=Decimal("200.00"),
        snapshot_time=report_day,
    )
    db_session.add_all([paid_snapshot, pending_snapshot])
    db_session.flush()
    db_session.add_all([
        Invoice(
            tenant_id=sample_tenant.id,
            session_id=valid_session.id,
            order_id=completed_order.id,
            pricing_snapshot_id=paid_snapshot.id,
            energy_kwh=Decimal("2.500"),
            duration_minutes=Decimal("30.00"),
            energy_cost=Decimal("2500.00"),
            service_fee=Decimal("200.00"),
            total_amount=Decimal("2700.00"),
            status="paid",
            issued_at=report_day,
        ),
        Invoice(
            tenant_id=sample_tenant.id,
            session_id=invalid_meter_session.id,
            order_id=pending_order.id,
            pricing_snapshot_id=pending_snapshot.id,
            energy_kwh=Decimal("99.000"),
            duration_minutes=Decimal("30.00"),
            energy_cost=Decimal("99000.00"),
            service_fee=Decimal("0.00"),
            total_amount=Decimal("99000.00"),
            status="pending",
            issued_at=report_day,
        ),
    ])
    db_session.commit()

    revenue = ReportService.get_revenue_report(
        db_session, sample_tenant.id, range_start, range_end, site_id=sample_site.id
    )
    energy = ReportService.get_energy_report(
        db_session, sample_tenant.id, range_start, range_end, site_id=sample_site.id
    )
    orders = ReportService.get_orders_report(
        db_session, sample_tenant.id, range_start, range_end, site_id=sample_site.id
    )

    assert revenue == [{
        "date": "2026-07-20",
        "total_revenue": Decimal("2700.00"),
        "total_energy_kwh": Decimal("2.500"),
        "invoice_count": 1,
        "currency": "COP",
    }]
    assert energy == [{
        "date": "2026-07-20",
        "total_energy_kwh": Decimal("2.5"),
        "session_count": 1,
    }]
    assert orders == [{
        "date": "2026-07-20",
        "order_count": 2,
        "completed_count": 1,
    }]


def test_report_api_uses_utc_inclusive_dates_site_scope_and_decimal_strings(
    admin_client,
    sample_site,
):
    report_rows = [{
        "date": "2026-07-20",
        "total_revenue": Decimal("2700.00"),
        "total_energy_kwh": Decimal("2.500"),
        "invoice_count": 1,
        "currency": "COP",
    }]
    with patch.object(ReportService, "get_revenue_report", return_value=report_rows) as loader:
        response = admin_client.get(
            "/api/v1/admin/statistics/revenue",
            params={
                "start_date": "2026-07-20",
                "end_date": "2026-07-20",
                "site_id": sample_site.site_code,
            },
        )

    assert response.status_code == 200
    assert response.json() == [{
        "date": "2026-07-20",
        "total_revenue": "2700.00",
        "total_energy_kwh": "2.500",
        "invoice_count": 1,
        "currency": "COP",
    }]
    call = loader.call_args.kwargs
    assert call["site_id"] == sample_site.id
    assert call["start_date"] == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert call["end_date"] == datetime(2026, 7, 21, tzinfo=timezone.utc)

    assert admin_client.get(
        "/api/v1/admin/statistics/revenue",
        params={"start_date": "2026-07-21", "end_date": "2026-07-20"},
    ).status_code == 422
    assert admin_client.get(
        "/api/v1/admin/statistics/revenue",
        params={"start_date": "2026-07-20"},
    ).status_code == 422


def test_report_export_reuses_query_filters_and_has_utf8_csv(
    admin_client,
    sample_site,
):
    csv_content = "date,total_revenue,total_energy_kwh,invoice_count,currency\r\n2026-07-20,2700.00,2.500,1,COP\r\n".encode("utf-8-sig")
    with patch.object(ReportService, "export_report", return_value=csv_content) as exporter:
        response = admin_client.get(
            "/api/v1/admin/statistics/export",
            params={
                "report_type": "revenue",
                "start_date": "2026-07-20",
                "end_date": "2026-07-20",
                "site_id": sample_site.site_code,
                "format": "csv",
            },
        )

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "text/csv" in response.headers["content-type"]
    call = exporter.call_args.kwargs
    assert call["report_type"] == "revenue"
    assert call["site_id"] == sample_site.id
    assert call["start_date"] == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert call["end_date"] == datetime(2026, 7, 21, tzinfo=timezone.utc)
