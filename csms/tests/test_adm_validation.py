"""Acceptance coverage for ADM-VALIDATION-001 backend contracts."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.auth import create_access_token, get_password_hash
from app.database.models import (
    AdminUser,
    AppUser,
    AppWalletTransaction,
    AuditLog,
    ChargingSession,
    ChargePoint,
    OutboxEvent,
    Role,
    Site,
    Tenant,
    TenantMembership,
    TenantMembershipRole,
)
from app.services.role_service import RoleService
from app.services.tenant_service import TenantService


def test_error_envelope_and_stable_validation_paths(admin_client):
    validation = admin_client.post(
        "/api/v1/sites",
        json={
            "name": "x",
            "address": "Valid address",
            "latitude": 4.7,
            "longitude": -74.1,
        },
    )
    assert validation.status_code == 422
    body = validation.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
    name_error = next(detail for detail in body["error"]["details"] if detail["field"] == "name")
    assert name_error["path"] == ["body", "name"]
    assert set(name_error) == {"field", "path", "message", "type"}

    missing = admin_client.get(f"/api/v1/sites/{uuid.uuid4()}")
    assert missing.status_code == 404
    error = missing.json()
    assert error["success"] is False
    assert error["error"]["message"] == "Site not found"
    assert error["error"]["details"] == []


def test_site_write_validation_and_uuid_boundary(admin_client, db_session):
    endpoint = "/api/v1/sites"
    invalid_payloads = [
        {"name": " ", "address": "Valid address", "latitude": 4.7, "longitude": -74.1},
        {"name": "Valid", "address": "   ", "latitude": 4.7, "longitude": -74.1},
        {"name": "Valid", "address": "Valid address", "latitude": 91, "longitude": -74.1},
        {"name": "Valid", "address": "Valid address", "latitude": 4.7, "longitude": 181},
        {"name": "Valid", "address": "Valid address", "latitude": 0, "longitude": 0},
    ]
    for payload in invalid_payloads:
        assert admin_client.post(endpoint, json=payload).status_code == 422

    response = admin_client.post(endpoint, json={
        "name": "  Bogotá Central  ",
        "address": "  Carrera 7 # 72-41  ",
        "latitude": 4.657,
        "longitude": -74.055,
        "operating_hours": "24/7",
    })
    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["site_code"].startswith("site_")
    assert "Bogotá" not in body["site_code"]
    site = db_session.query(Site).filter(Site.id == uuid.UUID(body["id"])).one()
    assert site.name == "Bogotá Central"
    assert site.address == "Carrera 7 # 72-41"


def test_charge_point_identity_validation_and_conflict(admin_client, db_session, sample_site):
    endpoint = f"/api/v1/sites/{sample_site.id}/charge-points"
    for identity in ("", "with space", "bad/identity", "x" * 65, "中文"):
        response = admin_client.post(
            endpoint,
            json={"id": identity, "display_code": "A01", "connector_count": 1},
        )
        assert response.status_code == 422

    for display_code in ("1A", "A_01", "A.01", "A:01", "A" * 17):
        response = admin_client.post(
            endpoint,
            json={"id": "CP-DISPLAY-VALIDATION", "display_code": display_code},
        )
        assert response.status_code == 422

    for field, value in (("display_name", "N" * 81), ("location_hint", "L" * 161)):
        response = admin_client.post(
            endpoint,
            json={"id": "CP-LABEL-LENGTH", "display_code": "A01", field: value},
        )
        assert response.status_code == 422

    unsupported_connector = admin_client.post(
        endpoint,
        json={
            "id": "CP-UNSUPPORTED-CONNECTOR",
            "display_code": "A02",
            "connector_type": "Type1",
        },
    )
    assert unsupported_connector.status_code == 422

    payload = {
        "id": "CP.demo_01:west",
        "display_code": " a01 ",
        "display_name": "  North entrance  ",
        "location_hint": "  P2 / bay 42  ",
        "connector_count": 1,
    }
    with patch("app.services.qr_service.generate_qr_code", return_value=Path("/tmp/test-qr.png")):
        first = admin_client.post(endpoint, json=payload)
    assert first.status_code == 201
    uuid.UUID(first.json()["id"])
    assert first.json()["ocpp_identity"] == payload["id"]
    assert first.json()["display_code"] == "A01"
    assert first.json()["display_name"] == "North entrance"
    assert first.json()["location_hint"] == "P2 / bay 42"
    assert first.json()["evses"][0]["physical_reference"] == "A01-1"
    assert admin_client.post(endpoint, json=payload).status_code == 409

    same_site_duplicate = admin_client.post(
        endpoint,
        json={"id": "CP.demo_02:west", "display_code": "a01", "connector_count": 1},
    )
    assert same_site_duplicate.status_code == 409

    other_site = Site(
        tenant_id=sample_site.tenant_id,
        name="Second display-code site",
        address="Carrera 7 # 72-41, Bogotá",
        latitude=4.658,
        longitude=-74.056,
        is_active=True,
    )
    db_session.add(other_site)
    db_session.commit()
    with patch("app.services.qr_service.generate_qr_code", return_value=Path("/tmp/test-qr.png")):
        cross_site = admin_client.post(
            f"/api/v1/sites/{other_site.id}/charge-points",
            json={"id": "CP.demo_03:west", "display_code": "A01", "connector_count": 1},
        )
    assert cross_site.status_code == 201


def _create_non_privileged_admin(db_session, tenant):
    admin = AdminUser(
        id=uuid.uuid4(),
        username="no-control",
        email="no-control@example.com",
        password_hash=get_password_hash("test-password"),
        is_active=True,
        is_super_admin=False,
    )
    membership = TenantMembership(
        id=uuid.uuid4(), tenant_id=tenant.id, admin_user_id=admin.id, is_primary=True, status="active"
    )
    role = Role(
        id=uuid.uuid4(), tenant_id=tenant.id, name="reader", permissions=["chargers.read"], scope="tenant"
    )
    db_session.add_all([admin, membership, role])
    db_session.flush()
    db_session.add(TenantMembershipRole(membership_id=membership.id, role_id=role.id))
    db_session.commit()
    return admin


def test_readonly_admin_cannot_create_site(client, db_session, sample_tenant):
    readonly = AdminUser(
        id=uuid.uuid4(),
        username="site-readonly",
        email="site-readonly@example.com",
        password_hash=get_password_hash("test-password"),
        is_active=True,
        is_super_admin=False,
    )
    membership = TenantMembership(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        admin_user_id=readonly.id,
        is_primary=True,
        status="active",
    )
    role = Role(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        name="site-readonly",
        permissions=["sites.read"],
        scope="tenant",
    )
    db_session.add_all([readonly, membership, role])
    db_session.flush()
    db_session.add(TenantMembershipRole(membership_id=membership.id, role_id=role.id))
    db_session.commit()

    token = create_access_token({
        "user_id": str(readonly.id),
        "user_type": "admin",
        "aud": "admin",
    })
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(sample_tenant.id),
    }
    before = db_session.query(Site).count()
    readable = client.get("/api/v1/sites", headers=headers)
    denied = client.post(
        "/api/v1/sites",
        headers=headers,
        json={
            "name": "Forbidden Site",
            "address": "Valid address Bogota",
            "latitude": 4.6,
            "longitude": -74.1,
        },
    )

    assert readable.status_code == 200
    assert denied.status_code == 403
    assert db_session.query(Site).count() == before


def test_remote_control_auth_permission_tenant_and_real_transaction(
    client, db_session, sample_tenant, sample_charge_point, sample_evse
):
    start_payload = {
        "charge_point_id": sample_charge_point.ocpp_identity,
        "id_tag": "ADMIN",
        "connector_id": 1,
    }
    client.headers.pop("Authorization", None)
    client.headers.update({"X-Tenant-Id": str(sample_tenant.id)})
    assert client.post("/api/v1/ocpp/remote-start-transaction", json=start_payload).status_code == 401

    no_control = _create_non_privileged_admin(db_session, sample_tenant)
    token = create_access_token({"user_id": str(no_control.id), "user_type": "admin", "aud": "admin"})
    denied = client.post(
        "/api/v1/ocpp/remote-start-transaction",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": str(sample_tenant.id)},
        json=start_payload,
    )
    assert denied.status_code == 403

    reader_headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(sample_tenant.id)}
    with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=True), patch(
        "app.api.v1.ocpp_control.message_handler.send_call",
        new=AsyncMock(return_value={"success": True}),
    ):
        readable = client.post(
            "/api/v1/ocpp/get-configuration",
            headers=reader_headers,
            json={"charge_point_id": sample_charge_point.ocpp_identity},
        )
    assert readable.status_code == 200
    assert client.get("/api/v1/ocpp/connected", headers=reader_headers).status_code == 200
    assert client.post(
        "/api/v1/ocpp/change-configuration",
        headers=reader_headers,
        json={"charge_point_id": sample_charge_point.ocpp_identity, "key": "k", "value": "v"},
    ).status_code == 403
    assert client.post(
        "/api/v1/ocpp/unlock-connector",
        headers=reader_headers,
        json={"charge_point_id": sample_charge_point.ocpp_identity, "connector_id": 1},
    ).status_code == 403

    super_admin = AdminUser(
        id=uuid.uuid4(), username="remote-super", email="remote-super@example.com",
        password_hash=get_password_hash("test-password"), is_active=True, is_super_admin=True,
    )
    db_session.add(super_admin)
    db_session.commit()
    super_token = create_access_token({"user_id": str(super_admin.id), "user_type": "admin", "aud": "admin"})
    client.headers.update({"Authorization": f"Bearer {super_token}"})

    other_tenant = Tenant(name="Other tenant", status="active")
    db_session.add(other_tenant)
    db_session.commit()
    client.headers.update({"X-Tenant-Id": str(other_tenant.id)})
    assert client.post("/api/v1/ocpp/reset", json={
        "charge_point_id": sample_charge_point.ocpp_identity, "type": "Soft"
    }).status_code == 403

    client.headers.update({"X-Tenant-Id": str(sample_tenant.id)})
    session = ChargingSession(
        tenant_id=sample_tenant.id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=88001,
        id_tag="ADMIN",
        start_time=datetime.now(timezone.utc),
        status="ongoing",
    )
    db_session.add(session)
    db_session.commit()

    with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=True), patch(
        "app.api.v1.ocpp_control.message_handler.send_call", new=AsyncMock(return_value={"success": True})
    ) as sender:
        wrong = client.post("/api/v1/ocpp/remote-stop-transaction", json={
            "charge_point_id": sample_charge_point.ocpp_identity,
            "transaction_id": sample_evse.evse_id,
        })
        assert wrong.status_code == 422

        headers = {"Idempotency-Key": "stop-88001"}
        first = client.post("/api/v1/ocpp/remote-stop-transaction", headers=headers, json={
            "charge_point_id": sample_charge_point.ocpp_identity,
            "transaction_id": session.transaction_id,
        })
        second = client.post("/api/v1/ocpp/remote-stop-transaction", headers=headers, json={
            "charge_point_id": sample_charge_point.ocpp_identity,
            "transaction_id": session.transaction_id,
        })
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["details"]["idempotent_replay"] is True
        sender.assert_awaited_once()
        assert sender.await_args.args[2] == {"transactionId": 88001}

    assert db_session.query(OutboxEvent).filter(OutboxEvent.idempotency_key == "remote-command:stop-88001").count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.action == "ocpp.remote_stop").count() == 1


def test_tenant_provision_success_and_service_rollback(admin_client, db_session, monkeypatch):
    payload = {
        "tenant": {"name": "Atomic Tenant", "domain": "atomic.example", "subscription_plan": "pro"},
        "admin": {
            "username": "atomic-admin",
            "email": "atomic-admin@example.com",
            "password": "StrongPassword!123",
            "full_name": "Atomic Admin",
        },
    }
    response = admin_client.post("/api/v1/admin/tenants/provision", json=payload)
    assert response.status_code == 201
    body = response.json()
    tenant_id = uuid.UUID(body["tenant"]["id"])
    assert body["tenant"]["subscription_plan"] == "pro"
    assert body["admin"]["username"] == "atomic-admin"
    assert body["admin"]["email"] == "atomic-admin@example.com"
    assert body["admin"]["is_super_admin"] is False
    assert "password" not in body["admin"]
    assert "temporary_password" not in body
    assert "admin_user_id" not in body
    uuid.UUID(body["membership_id"])
    assert db_session.query(TenantMembership).filter(TenantMembership.tenant_id == tenant_id).count() == 1

    before_tenants = db_session.query(Tenant).count()
    before_admins = db_session.query(AdminUser).count()

    def fail_role(*args, **kwargs):
        raise RuntimeError("forced role failure")

    monkeypatch.setattr(RoleService, "ensure_default_tenant_admin_role", fail_role)
    with pytest.raises(RuntimeError, match="forced role failure"):
        TenantService.provision_tenant(
            db_session,
            tenant_data={"name": "Rollback Tenant", "domain": "rollback.example", "settings": {}},
            admin_data={
                "username": "rollback-admin",
                "email": "rollback-admin@example.com",
                "password": "StrongPassword!123",
                "full_name": None,
            },
        )
    assert db_session.query(Tenant).count() == before_tenants
    assert db_session.query(AdminUser).count() == before_admins


def test_tenant_contract_plan_password_and_own_settings(admin_client, db_session, sample_tenant):
    provision_url = "/api/v1/admin/tenants/provision"
    base_payload = {
        "tenant": {"name": "Contract Tenant", "domain": "contract.example", "subscription_plan": "pro"},
        "admin": {
            "username": "contract-admin",
            "email": "contract-admin@example.com",
            "password": "12345678",
        },
    }
    for legacy_plan in ("basic", "premium"):
        invalid = {
            **base_payload,
            "tenant": {**base_payload["tenant"], "subscription_plan": legacy_plan},
        }
        assert admin_client.post(provision_url, json=invalid).status_code == 422

    too_short = {
        **base_payload,
        "admin": {**base_payload["admin"], "password": "1234567"},
    }
    assert admin_client.post(provision_url, json=too_short).status_code == 422
    too_long = {
        **base_payload,
        "admin": {**base_payload["admin"], "password": "x" * 129},
    }
    assert admin_client.post(provision_url, json=too_long).status_code == 422
    assert admin_client.post(provision_url, json=base_payload).status_code == 201

    sample_tenant.settings = {"protected": True}
    db_session.commit()
    current_url = "/api/v1/admin/tenants/current"
    assert admin_client.put(current_url, json={"settings": {"protected": False}}).status_code == 422
    assert admin_client.put(current_url, json={"name": "x"}).status_code == 422
    assert admin_client.put(current_url, json={"domain": "bad domain"}).status_code == 422

    updated = admin_client.put(
        current_url,
        json={"name": "  Renamed Tenant  ", "domain": "renamed.example"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Tenant"
    assert updated.json()["domain"] == "renamed.example"
    assert updated.json()["settings"] == {"protected": True}


def test_wallet_adjustment_decimal_reason_idempotency_and_audit(admin_client, db_session, sample_tenant):
    user = AppUser(
        email="wallet-adm@example.com",
        password_hash=get_password_hash("test-password"),
        balance=Decimal("100.00"),
        status="active",
    )
    db_session.add(user)
    db_session.commit()

    endpoint = f"/api/v1/admin/app-users/{user.id}/adjust-balance"
    assert admin_client.post(endpoint, json={
        "amount": "1.001", "description": "precision", "idempotency_key": "precision-001"
    }).status_code == 422
    assert admin_client.post(endpoint, json={
        "amount": "10.25", "description": " ", "idempotency_key": "reason-001"
    }).status_code == 422

    payload = {"amount": "10.25", "description": "Manual reconciliation", "idempotency_key": "adjust-001"}
    first = admin_client.post(endpoint, json=payload)
    second = admin_client.post(endpoint, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["transaction_id"] == second.json()["transaction_id"]
    db_session.expire_all()
    assert db_session.query(AppUser).filter(AppUser.id == user.id).one().balance == Decimal("110.25")
    assert db_session.query(AppWalletTransaction).filter_by(idempotency_key="adjust-001").count() == 1
    assert db_session.query(AuditLog).filter(AuditLog.action == "wallet.adjust_balance").count() == 1


def test_config_registry_rejects_unknown_key(admin_client):
    unknown = admin_client.post("/api/v1/admin/configs", json={
        "config_key": "arbitrary_pollution", "config_value": "yes", "value_type": "string"
    })
    assert unknown.status_code == 422

    valid = admin_client.post("/api/v1/admin/configs", json={
        "config_key": "max_charging_power", "config_value": "120.5", "value_type": "float"
    })
    assert valid.status_code == 200
    assert valid.json()["config_value"] == 120.5
