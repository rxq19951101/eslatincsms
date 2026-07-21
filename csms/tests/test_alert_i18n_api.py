"""ALERT-I18N-001 backend contract regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from sqlalchemy import event

from app.api.v1.admin.alerts import (
    CreateAlertRequest,
    acknowledge_alert,
    create_alert,
    get_alert,
    list_alerts,
    resolve_alert,
    serialize_alert,
)
from app.core.auth import get_password_hash
from app.database.base import tenant_id_context
from app.database.models import AdminUser, Alert, ChargePoint, EVSE, Site, Tenant
from app.services.alert_service import AlertService


@pytest.mark.asyncio
async def test_all_alert_response_endpoints_share_structured_context(
    db_session, sample_tenant, sample_site, sample_charge_point, sample_evse
):
    sample_site.site_code = "site_0123456789abcdef"
    sample_site.name = "SIM E2E Test Site"
    sample_site.address = "Calle 100 # 10-20, Bogota"
    sample_charge_point.model = "Simulated 7kW"
    sample_charge_point.serial_number = "SIM-001"
    sample_evse.physical_reference = "Bay 1"
    admin = AdminUser(
        id=uuid.uuid4(),
        username="alert-i18n-admin",
        email="alert-i18n-admin@example.com",
        password_hash=get_password_hash("test-password"),
        is_active=True,
        is_super_admin=True,
    )
    db_session.add(admin)
    db_session.commit()

    current_user = SimpleNamespace(id=admin.id, is_super_admin=True)
    context_token = tenant_id_context.set(sample_tenant.id)
    try:
        with patch(
            "app.services.notification_service.NotificationService.send_alert_notification",
            new=AsyncMock(),
        ):
            created = await create_alert(
                request_data=CreateAlertRequest(
                    alert_type="operator_note",
                    severity="warning",
                    title="Manual inspection required",
                    description="OCPP vendor message",
                    charge_point_id=sample_charge_point.ocpp_identity,
                    evse_id=sample_evse.id,
                    metadata={"ticket": "OPS-17"},
                ),
                current_user_obj=current_user,
                db=db_session,
            )

        listed = await list_alerts(
            skip=0,
            limit=100,
            status=None,
            severity=None,
            alert_type=None,
            charge_point_id=None,
            current_user_obj=current_user,
            db=db_session,
        )
        detailed = await get_alert(
            alert_id=uuid.UUID(created.id),
            current_user_obj=current_user,
            db=db_session,
        )
        acknowledged = await acknowledge_alert(
            alert_id=uuid.UUID(created.id),
            current_user_obj=current_user,
            db=db_session,
        )
        resolved = await resolve_alert(
            alert_id=uuid.UUID(created.id),
            current_user_obj=current_user,
            db=db_session,
        )
    finally:
        tenant_id_context.reset(context_token)

    responses = [created, listed[0], detailed, acknowledged, resolved]
    for response in responses:
        assert response.alert_code == "manual"
        assert response.message_params == {"ticket": "OPS-17"}
        assert response.raw_message == "OCPP vendor message"
        assert response.site.dict() == {
            "site_code": "site_0123456789abcdef",
            "name": "SIM E2E Test Site",
            "address": "Calle 100 # 10-20, Bogota",
        }
        assert response.charge_point.dict() == {
            "ocpp_identity": sample_charge_point.ocpp_identity,
            "model": "Simulated 7kW",
            "serial_number": "SIM-001",
        }
        assert response.evse.dict() == {
            "evse_id": 1,
            "physical_reference": "Bay 1",
        }

    assert created.status == "pending"
    assert acknowledged.status == "acknowledged"
    assert resolved.status == "resolved"


@pytest.mark.parametrize(
    ("alert_type", "metadata", "expected_code", "expected_params"),
    [
        (
            "offline",
            {"source": "heartbeat_timeout", "timeout_seconds": 90},
            "charger.offline.heartbeat_timeout",
            {"timeout_seconds": 90},
        ),
        (
            "offline",
            {"source": "websocket_disconnect"},
            "charger.offline.websocket_disconnected",
            {},
        ),
        (
            "faulted",
            {"source": "StatusNotification", "error_code": "GroundFailure"},
            "charger.faulted",
            {"error_code": "GroundFailure"},
        ),
        (
            "temperature",
            {"event_id": 42, "rule_id": "rule-1"},
            "device.event",
            {"event_id": 42, "rule_id": "rule-1"},
        ),
    ],
)
def test_p0_alert_codes_and_message_params(
    db_session,
    sample_tenant,
    alert_type,
    metadata,
    expected_code,
    expected_params,
):
    alert = Alert(
        tenant_id=sample_tenant.id,
        alert_type=alert_type,
        dedupe_key=f"test:{alert_type}:{uuid.uuid4()}",
        severity="critical",
        status="pending",
        title="Legacy title",
        description="Raw device message",
        alert_metadata=metadata,
    )
    db_session.add(alert)
    db_session.commit()

    response = serialize_alert(alert)

    assert response.alert_code == expected_code
    assert response.message_params == expected_params
    assert response.raw_message == "Raw device message"
    assert response.site is None
    assert response.charge_point is None
    assert response.evse is None


def test_alert_context_suppresses_cross_tenant_relationships(db_session, sample_tenant):
    other_tenant = Tenant(id=uuid.uuid4(), name="Other tenant", status="active")
    other_site = Site(
        tenant_id=other_tenant.id,
        name="Secret site",
        address="Secret tenant address",
        latitude=4.7,
        longitude=-74.1,
    )
    other_charge_point = ChargePoint(
        tenant_id=other_tenant.id,
        site=other_site,
        ocpp_identity="OTHER-TENANT-CP",
        model="Secret model",
    )
    other_evse = EVSE(
        tenant_id=other_tenant.id,
        charge_point=other_charge_point,
        evse_id=9,
        physical_reference="Secret bay",
    )
    alert = Alert(
        tenant_id=sample_tenant.id,
        charge_point=other_charge_point,
        evse=other_evse,
        alert_type="offline",
        severity="critical",
        status="pending",
        title="Invalid cross-tenant relation",
        description=None,
        alert_metadata={"source": "heartbeat_timeout", "timeout_seconds": 90},
    )
    db_session.add_all([other_tenant, other_site, other_charge_point, other_evse, alert])
    db_session.commit()

    response = serialize_alert(alert)

    assert response.site is None
    assert response.charge_point is None
    assert response.evse is None
    assert response.raw_message is None


def test_list_alerts_eager_loads_all_serializer_relationships(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    tenant_id = sample_tenant.id
    alerts = [
        Alert(
            tenant_id=tenant_id,
            charge_point_id=sample_charge_point.id,
            evse_id=sample_evse.id,
            alert_type="faulted",
            severity="critical",
            status="pending",
            title="Faulted",
            description="GroundFailure",
            alert_metadata={"source": "StatusNotification"},
        ),
        Alert(
            tenant_id=tenant_id,
            charge_point_id=None,
            evse_id=sample_evse.id,
            alert_type="offline",
            severity="warning",
            status="pending",
            title="Offline",
            description="Heartbeat timeout",
            alert_metadata={"source": "heartbeat_timeout", "timeout_seconds": 90},
        ),
    ]
    db_session.add_all(alerts)
    db_session.commit()
    db_session.expire_all()

    select_statements = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_select)
    try:
        loaded_alerts = AlertService.list_alerts(db_session, tenant_id=tenant_id)
        responses = [serialize_alert(alert) for alert in loaded_alerts]
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert len(responses) == 2
    assert all(response.site is not None for response in responses)
    assert all(response.charge_point is not None for response in responses)
    assert all(response.evse is not None for response in responses)
    assert len(select_statements) == 1
