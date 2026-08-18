"""BE-4 Charging Payment Intent and start binding tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import asyncio
import uuid

from app.core.auth import create_access_token, get_password_hash
from app.database.models import AppUser, Order, QrToken
from app.services.charging_payment_intent import create_payment_intent_data
from app.services.ocpp_message_handler import OCPPMessageHandler


def _user(db_session, *, email: str, balance: Decimal = Decimal("0.00")) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        email=email,
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=balance,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(user: AppUser) -> dict[str, str]:
    token = create_access_token(
        {"user_id": str(user.id), "user_type": "app_user", "aud": "app"}
    )
    return {"Authorization": f"Bearer {token}"}


def _intent_order(db_session, user, charge_point, evse, *, status="ready", expires=None):
    intent = create_payment_intent_data(
        app_user_id=user.id,
        charge_point_id=charge_point.id,
        connector_id=evse.evse_id,
        operator_tenant_id=charge_point.tenant_id,
        checkout_session_id="checkout-be4-test-opaque",
        expires_at=expires or datetime.now(timezone.utc) + timedelta(minutes=10),
        payment_method={"mode": "new_card", "save_card": False},
        merchant_snapshot={
            "merchant_mode": "platform",
            "merchant_account_ref": "platform:eslatin",
            "provider": "mercadopago",
        },
    )
    intent["status"] = status
    order = Order(
        tenant_id=charge_point.tenant_id,
        charge_point_id=charge_point.id,
        user_id=str(user.id),
        app_user_id=user.id,
        id_tag=f"APP{str(user.id).replace('-', '')[:17]}",
        pre_authorization=intent,
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order, intent["intent_id"]


def _qr(db_session, tenant, charge_point, connector_id):
    qr = QrToken(
        token=f"be4-qr-{uuid.uuid4().hex}",
        operator_tenant_id=tenant.id,
        charge_point_id=charge_point.id,
        connector_id=connector_id,
    )
    db_session.add(qr)
    db_session.commit()
    return qr


def test_direct_card_start_claims_intent_without_wallet_balance(
    client, db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user = _user(db_session, email="be4-direct@example.test")
    order, intent_id = _intent_order(
        db_session, user, sample_commercial_charge_point, sample_evse
    )
    qr = _qr(db_session, sample_tenant, sample_commercial_charge_point, sample_evse.evse_id)

    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new=AsyncMock(return_value={"success": True, "status": "Accepted"}),
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(user),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )

    assert response.status_code == 200
    sender.assert_awaited_once()
    db_session.refresh(order)
    assert order.pre_authorization["status"] == "start_requested"
    assert order.pre_authorization["intent_id"] == intent_id


def test_direct_card_start_rejects_wrong_user_and_connector(
    client, db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    owner = _user(db_session, email="be4-owner@example.test")
    intruder = _user(db_session, email="be4-intruder@example.test")
    _, intent_id = _intent_order(
        db_session, owner, sample_commercial_charge_point, sample_evse
    )
    qr = _qr(db_session, sample_tenant, sample_commercial_charge_point, sample_evse.evse_id)

    with patch(
        "app.api.v1.app.charging.send_remote_start", new=AsyncMock()
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(intruder),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAYMENT_INTENT_INVALID"
    sender.assert_not_awaited()


def test_remote_start_rejection_returns_intent_to_ready(
    client, db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user = _user(db_session, email="be4-retry@example.test")
    order, intent_id = _intent_order(
        db_session, user, sample_commercial_charge_point, sample_evse
    )
    qr = _qr(db_session, sample_tenant, sample_commercial_charge_point, sample_evse.evse_id)

    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new=AsyncMock(return_value={"success": False, "status": "Rejected"}),
    ):
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(user),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )

    assert response.status_code == 409
    db_session.refresh(order)
    assert order.pre_authorization["status"] == "ready"


def test_expired_payment_intent_is_rejected_and_not_sent_to_device(
    client, db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user = _user(db_session, email="be4-expired@example.test")
    order, intent_id = _intent_order(
        db_session,
        user,
        sample_commercial_charge_point,
        sample_evse,
        expires=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    qr = _qr(db_session, sample_tenant, sample_commercial_charge_point, sample_evse.evse_id)

    with patch(
        "app.api.v1.app.charging.send_remote_start", new=AsyncMock()
    ) as sender:
        response = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(user),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )

    assert response.status_code == 409
    sender.assert_not_awaited()
    db_session.refresh(order)
    assert order.pre_authorization["status"] == "expired"


def test_replayed_start_cannot_send_remote_start_twice(
    client, db_session, sample_tenant, sample_commercial_charge_point, sample_evse
):
    user = _user(db_session, email="be4-replay@example.test")
    order, intent_id = _intent_order(
        db_session, user, sample_commercial_charge_point, sample_evse
    )
    qr = _qr(db_session, sample_tenant, sample_commercial_charge_point, sample_evse.evse_id)
    with patch(
        "app.api.v1.app.charging.send_remote_start",
        new=AsyncMock(return_value={"success": True, "status": "Accepted"}),
    ) as sender:
        first = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(user),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )
        second = client.post(
            "/api/v1/app/charging/start",
            headers=_headers(user),
            json={
                "qr_token": qr.token,
                "settlement_method": "direct_card",
                "payment_intent_id": intent_id,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "PAYMENT_INTENT_INVALID"
    sender.assert_awaited_once()
    db_session.refresh(order)
    assert order.pre_authorization["status"] == "start_requested"


def test_start_transaction_binds_one_intent_order_to_one_session(
    db_session, sample_charge_point, sample_commercial_charge_point, sample_evse
):
    user = _user(db_session, email="be4-bind@example.test")
    order, _ = _intent_order(
        db_session, user, sample_commercial_charge_point, sample_evse, status="start_requested"
    )
    handler = OCPPMessageHandler()

    response = asyncio.run(
        handler.handle_start_transaction(
            charge_point_id=sample_commercial_charge_point.ocpp_identity,
            payload={
                "connectorId": sample_evse.evse_id,
                "idTag": order.id_tag,
                "meterStart": 0,
            },
            evse_id=sample_evse.evse_id,
            db=db_session,
        )
    )

    assert response["idTagInfo"]["status"] == "Accepted"
    db_session.refresh(order)
    assert order.session_id is not None
    assert order.pre_authorization["status"] == "bound"
    assert order.pre_authorization["session_id"] == str(order.session_id)
