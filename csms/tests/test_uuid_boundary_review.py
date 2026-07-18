"""Directed regression coverage for UUID/OCPP identity boundary review items."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import json
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.app.charging import check_charger_status
from app.api.v1.charger_management import get_pending_chargers
from app.api.v1.orders import list_orders
from app.api.v1.statistics import get_charger_heartbeat_history
from app.api.v1.transactions import list_transactions
from app.api.v1.admin.alerts import create_alert, list_alerts, CreateAlertRequest
from app.core.asset_identifiers import (
    get_charge_point_by_internal_id,
    get_charge_point_by_reference,
    get_tenant_charge_point_by_reference,
)
from app.core.auth import get_password_hash
from app.database.base import tenant_id_context
from app.database.models import (
    Alert,
    AppUser,
    ChargePoint,
    ChargingSession,
    DeviceEvent,
    Order,
    Tenant,
)


def test_uuid_shaped_ocpp_identity_is_resolved_before_internal_uuid(
    db_session, sample_site
):
    ambiguous_uuid = uuid.uuid4()
    identity_charge_point = ChargePoint(
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity=str(ambiguous_uuid),
        vendor="Identity match",
    )
    internal_charge_point = ChargePoint(
        id=ambiguous_uuid,
        tenant_id=sample_site.tenant_id,
        site_id=sample_site.id,
        ocpp_identity="CP-INTERNAL-MATCH",
        vendor="Internal match",
    )
    db_session.add_all([identity_charge_point, internal_charge_point])
    db_session.commit()

    assert get_charge_point_by_reference(db_session, str(ambiguous_uuid)).id == identity_charge_point.id
    assert get_charge_point_by_internal_id(db_session, str(ambiguous_uuid)).id == internal_charge_point.id
    assert get_tenant_charge_point_by_reference(
        db_session, str(ambiguous_uuid), sample_site.tenant_id
    ).id == identity_charge_point.id


@pytest.mark.asyncio
async def test_websocket_boot_dispatch_keeps_path_identity():
    from app.main import _handle_ocpp_websocket_messages

    path_identity = "CP-PATH-IDENTITY"
    payload = {"serialNumber": "PAYLOAD-SERIAL"}
    ws = SimpleNamespace(
        receive_text=AsyncMock(side_effect=[
            json.dumps([2, "boot-1", "BootNotification", payload]),
            RuntimeError("stop loop"),
        ]),
        send_text=AsyncMock(),
    )
    identity_ref = {"value": path_identity}

    with patch(
        "app.main.handle_ocpp_message",
        new=AsyncMock(return_value={"status": "Accepted", "currentTime": "now", "interval": 30}),
    ) as handler:
        with pytest.raises(RuntimeError, match="stop loop"):
            await _handle_ocpp_websocket_messages(ws, identity_ref)

    assert identity_ref["value"] == path_identity
    assert handler.await_args.kwargs["charge_point_id"] == path_identity
    assert handler.await_args.kwargs["device_serial_number"] is None
    assert handler.await_args.kwargs["payload"]["serialNumber"] == "PAYLOAD-SERIAL"


def test_qr_check_uses_ocpp_identity_and_returns_both_ids(
    db_session, sample_charge_point, sample_evse, sample_evse_status
):
    app_user = AppUser(
        email="uuid-boundary-app@example.com",
        password_hash=get_password_hash("test-password"),
        balance=100000,
        has_unpaid_charges=False,
    )
    sample_evse_status.last_seen = datetime.now(timezone.utc)
    db_session.add(app_user)
    db_session.commit()
    token_record = SimpleNamespace(
        charge_point_id=sample_charge_point.id,
        connector_id=sample_evse.evse_id,
    )

    with patch("app.api.v1.app.charging.SuperSessionLocal", return_value=db_session), patch(
        "app.api.v1.app.charging.resolve_qr_token", return_value=token_record
    ), patch(
        "app.api.v1.app.charging.check_charger_connection", return_value=True
    ) as connection_check:
        result = check_charger_status("valid-qr-token", app_user)

    connection_check.assert_called_once_with(sample_charge_point.ocpp_identity)
    assert result["charge_point_id"] == str(sample_charge_point.id)
    assert result["charger_id"] == str(sample_charge_point.id)
    assert result["ocpp_identity"] == sample_charge_point.ocpp_identity


def test_pending_chargers_query_connected_ocpp_identity_with_tenant_scope(
    db_session, sample_tenant, sample_charge_point
):
    context_token = tenant_id_context.set(sample_tenant.id)
    try:
        with patch(
            "app.ocpp.connection_manager.connection_manager.get_all_charger_ids",
            return_value=[sample_charge_point.ocpp_identity],
        ), patch(
            "app.api.v1.charger_management.get_charger_from_redis",
            return_value={"status": "Available"},
        ):
            pending = get_pending_chargers(
                current_user_obj=SimpleNamespace(is_super_admin=True),
                db=db_session,
            )
    finally:
        tenant_id_context.reset(context_token)

    assert len(pending) == 1
    assert pending[0].charger_id == sample_charge_point.ocpp_identity
    assert pending[0].is_configured is True


@pytest.mark.asyncio
async def test_string_charge_point_filters_resolve_identity_and_enforce_tenant(
    db_session, sample_tenant, sample_charge_point, sample_evse
):
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=99101,
        id_tag="BOUNDARY",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    order = Order(
        id="ORDER-UUID-BOUNDARY",
        tenant_id=sample_tenant.id,
        charge_point_id=sample_charge_point.id,
        user_id="boundary-user",
        id_tag="BOUNDARY",
        status="pending",
    )
    db_session.add_all([session, order])
    db_session.commit()
    admin = SimpleNamespace(id=uuid.uuid4(), is_super_admin=True)
    context_token = tenant_id_context.set(sample_tenant.id)
    try:
        transactions = list_transactions(
            charge_point_id=sample_charge_point.ocpp_identity,
            status=None,
            limit=100,
            offset=0,
            current_user_obj=admin,
            db=db_session,
        )
        orders = list_orders(
            user_id=None,
            charge_point_id=sample_charge_point.ocpp_identity,
            session_id=None,
            status=None,
            limit=100,
            offset=0,
            current_user_obj=admin,
            db=db_session,
        )
        stats = get_charger_heartbeat_history(
            charge_point_id=sample_charge_point.ocpp_identity,
            hours=24,
            current_user_obj=admin,
            db=db_session,
        )
        with patch(
            "app.services.notification_service.NotificationService.send_alert_notification",
            new=AsyncMock(),
        ):
            alert = await create_alert(
                request_data=CreateAlertRequest(
                    alert_type="offline",
                    severity="warning",
                    title="Boundary alert",
                    charge_point_id=sample_charge_point.ocpp_identity,
                ),
                current_user_obj=admin,
                db=db_session,
            )
        alerts = await list_alerts(
            skip=0,
            limit=100,
            status=None,
            severity=None,
            alert_type=None,
            charge_point_id=sample_charge_point.ocpp_identity,
            current_user_obj=admin,
            db=db_session,
        )
    finally:
        tenant_id_context.reset(context_token)

    assert transactions[0]["charge_point_id"] == str(sample_charge_point.id)
    assert transactions[0]["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert orders[0]["charge_point_id"] == str(sample_charge_point.id)
    assert orders[0]["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert stats["charge_point_id"] == str(sample_charge_point.id)
    assert stats["ocpp_identity"] == sample_charge_point.ocpp_identity
    assert alert.charge_point_id == str(sample_charge_point.id)
    assert alerts[0].charge_point_id == str(sample_charge_point.id)
    assert db_session.query(Alert).filter(Alert.charge_point_id == sample_charge_point.id).count() == 1

    other_tenant = Tenant(name="Boundary other tenant", status="active")
    db_session.add(other_tenant)
    db_session.commit()
    other_context = tenant_id_context.set(other_tenant.id)
    try:
        with pytest.raises(HTTPException) as exc_info:
            list_transactions(
                charge_point_id=sample_charge_point.ocpp_identity,
                status=None,
                limit=100,
                offset=0,
                current_user_obj=admin,
                db=db_session,
            )
        assert exc_info.value.status_code == 404
        with pytest.raises(HTTPException) as exc_info:
            list_orders(
                user_id=None,
                charge_point_id=sample_charge_point.ocpp_identity,
                session_id=None,
                status=None,
                limit=100,
                offset=0,
                current_user_obj=admin,
                db=db_session,
            )
        assert exc_info.value.status_code == 404
        with pytest.raises(HTTPException) as exc_info:
            get_charger_heartbeat_history(
                charge_point_id=sample_charge_point.ocpp_identity,
                hours=24,
                current_user_obj=admin,
                db=db_session,
            )
        assert exc_info.value.status_code == 404
        with pytest.raises(HTTPException) as exc_info:
            await list_alerts(
                skip=0,
                limit=100,
                status=None,
                severity=None,
                alert_type=None,
                charge_point_id=sample_charge_point.ocpp_identity,
                current_user_obj=admin,
                db=db_session,
            )
        assert exc_info.value.status_code == 404
    finally:
        tenant_id_context.reset(other_context)
