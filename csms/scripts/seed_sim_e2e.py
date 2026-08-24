#!/usr/bin/env python3
"""Idempotently seed the frozen SIM-E2E-001 development/test dataset."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import get_password_hash
from app.database.base import SessionLocal, database_access_scope
from app.database.models import (
    AdminUser,
    Alert,
    AppUser,
    AppWalletTransaction,
    ChargePoint,
    ChargingSession,
    EVSE,
    EVSEStatus,
    PaymentOrder,
    QrToken,
    Role,
    Site,
    Tariff,
    Tenant,
    TenantMembership,
    TenantMembershipRole,
)


NAMESPACE = uuid.UUID("a5351816-899c-4be4-b8d6-4cc1e9d0dd93")


def stable_id(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


def required_password(name: str) -> str:
    value = os.getenv(name, "")
    if not 8 <= len(value) <= 128:
        raise SystemExit(f"{name} must be provided with 8-128 characters")
    return value


@database_access_scope("system")
def main() -> None:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment not in {"development", "test"}:
        raise SystemExit("SIM-E2E seed is disabled outside development/test")

    admin_password = required_password("SIM_E2E_ADMIN_PASSWORD")
    app_password = required_password("SIM_E2E_APP_PASSWORD")
    readonly_password = required_password("SIM_E2E_READONLY_PASSWORD")
    ids = {name: stable_id(name) for name in (
        "tenant", "admin", "membership", "role", "membership-role", "app-user",
        "wallet-top-up", "site", "charge-point", "evse", "evse-status", "tariff", "qr",
        "tenant-b", "tenant-b-site", "tenant-b-charge-point", "tenant-b-evse",
        "tenant-b-evse-status", "tenant-b-qr", "readonly-admin", "readonly-role",
        "readonly-membership", "readonly-membership-role", "low-balance-app-user",
        "other-app-user", "other-charge-point", "other-evse", "other-evse-status",
        "other-qr", "ownership-session", "charging-payment-order",
        "top-up-payment-order", "fault-alert",
    )}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    qr_token = f"sim_e2e_{uuid.uuid5(NAMESPACE, 'qr-token').hex}"
    other_qr_token = f"sim_e2e_other_{uuid.uuid5(NAMESPACE, 'other-qr-token').hex}"
    tenant_b_qr_token = f"sim_e2e_tenant_b_{uuid.uuid5(NAMESPACE, 'tenant-b-qr-token').hex}"

    db = SessionLocal()
    try:
        tenant = db.get(Tenant, ids["tenant"]) or Tenant(id=ids["tenant"])
        tenant.name = "SIM E2E Tenant"
        tenant.domain = "sim-e2e.local"
        tenant.status = "active"
        tenant.subscription_plan = "pro"
        db.add(tenant)

        tenant_b = db.get(Tenant, ids["tenant-b"]) or Tenant(id=ids["tenant-b"])
        tenant_b.name = "SIM E2E Tenant B"
        tenant_b.domain = "sim-e2e-b.local"
        tenant_b.status = "active"
        tenant_b.subscription_plan = "pro"
        db.add(tenant_b)

        admin = db.get(AdminUser, ids["admin"]) or AdminUser(id=ids["admin"])
        admin.username = "sim_e2e_admin"
        admin.email = "sim-e2e-admin@example.test"
        admin.password_hash = get_password_hash(admin_password)
        admin.full_name = "SIM E2E Admin"
        admin.is_active = True
        admin.is_super_admin = False
        db.add(admin)

        role = db.get(Role, ids["role"]) or Role(id=ids["role"])
        role.tenant_id = tenant.id
        role.name = "sim_e2e_operator"
        role.scope = "tenant"
        role.permissions = [
            "chargers.read", "chargers.control", "chargers.create", "sites.read",
            "sites.write", "alerts.read", "alerts.write", "transactions.read",
            "users.read", "wallet.adjust",
        ]
        role.description = "Deterministic SIM-E2E operator role"
        db.add(role)

        membership = db.get(TenantMembership, ids["membership"]) or TenantMembership(
            id=ids["membership"]
        )
        membership.tenant_id = tenant.id
        membership.admin_user_id = admin.id
        membership.is_primary = True
        membership.status = "active"
        db.add(membership)

        membership_role = db.get(
            TenantMembershipRole, ids["membership-role"]
        ) or TenantMembershipRole(id=ids["membership-role"])
        membership_role.membership_id = membership.id
        membership_role.role_id = role.id
        db.add(membership_role)

        readonly_admin = db.get(AdminUser, ids["readonly-admin"]) or AdminUser(
            id=ids["readonly-admin"]
        )
        readonly_admin.username = "sim_e2e_readonly"
        readonly_admin.email = "sim-e2e-readonly@example.test"
        readonly_admin.password_hash = get_password_hash(readonly_password)
        readonly_admin.full_name = "SIM E2E Read-only Admin"
        readonly_admin.is_active = True
        readonly_admin.is_super_admin = False
        db.add(readonly_admin)

        readonly_role = db.get(Role, ids["readonly-role"]) or Role(
            id=ids["readonly-role"]
        )
        readonly_role.tenant_id = tenant.id
        readonly_role.name = "sim_e2e_readonly"
        readonly_role.scope = "tenant"
        readonly_role.permissions = ["chargers.read", "sites.read", "alerts.read"]
        readonly_role.description = "Deterministic SIM-E2E read-only role"
        db.add(readonly_role)

        readonly_membership = db.get(
            TenantMembership, ids["readonly-membership"]
        ) or TenantMembership(id=ids["readonly-membership"])
        readonly_membership.tenant_id = tenant.id
        readonly_membership.admin_user_id = readonly_admin.id
        readonly_membership.is_primary = True
        readonly_membership.status = "active"
        db.add(readonly_membership)

        readonly_membership_role = db.get(
            TenantMembershipRole, ids["readonly-membership-role"]
        ) or TenantMembershipRole(id=ids["readonly-membership-role"])
        readonly_membership_role.membership_id = readonly_membership.id
        readonly_membership_role.role_id = readonly_role.id
        db.add(readonly_membership_role)

        app_user = db.get(AppUser, ids["app-user"]) or AppUser(id=ids["app-user"])
        app_user.email = "sim-e2e-app@example.test"
        app_user.phone = "+570000000001"
        app_user.full_name = "SIM E2E App User"
        app_user.password_hash = get_password_hash(app_password)
        app_user.email_verified = True
        app_user.status = "active"
        app_user.balance = Decimal("100000.00")
        app_user.has_unpaid_charges = False
        db.add(app_user)

        low_balance_user = db.get(
            AppUser, ids["low-balance-app-user"]
        ) or AppUser(id=ids["low-balance-app-user"])
        low_balance_user.email = "sim-e2e-low-balance@example.test"
        low_balance_user.phone = "+570000000002"
        low_balance_user.full_name = "SIM E2E Low Balance User"
        low_balance_user.password_hash = get_password_hash(app_password)
        low_balance_user.email_verified = True
        low_balance_user.status = "active"
        low_balance_user.balance = Decimal("0.00")
        low_balance_user.has_unpaid_charges = False
        db.add(low_balance_user)

        other_app_user = db.get(
            AppUser, ids["other-app-user"]
        ) or AppUser(id=ids["other-app-user"])
        other_app_user.email = "sim-e2e-other-app@example.test"
        other_app_user.phone = "+570000000003"
        other_app_user.full_name = "SIM E2E Other App User"
        other_app_user.password_hash = get_password_hash(app_password)
        other_app_user.email_verified = True
        other_app_user.status = "active"
        other_app_user.balance = Decimal("50000.00")
        other_app_user.has_unpaid_charges = True
        db.add(other_app_user)

        site = db.get(Site, ids["site"]) or Site(id=ids["site"])
        site.site_code = "site_51e2e00151e2e001"
        site.tenant_id = tenant.id
        site.name = "SIM E2E Test Site"
        site.address = "Calle 100 # 10-20, Bogota"
        site.latitude = 4.6872
        site.longitude = -74.0565
        site.is_active = True
        db.add(site)

        tenant_b_site = db.get(Site, ids["tenant-b-site"]) or Site(
            id=ids["tenant-b-site"]
        )
        tenant_b_site.site_code = "site_b1e2e001b1e2e001"
        tenant_b_site.tenant_id = tenant_b.id
        tenant_b_site.name = "SIM E2E Tenant B Site"
        tenant_b_site.address = "Carrera 7 # 71-21, Bogota"
        tenant_b_site.latitude = 4.6534
        tenant_b_site.longitude = -74.0567
        tenant_b_site.is_active = True
        db.add(tenant_b_site)

        charger = db.get(ChargePoint, ids["charge-point"]) or ChargePoint(
            id=ids["charge-point"]
        )
        charger.tenant_id = tenant.id
        charger.site_id = site.id
        charger.ocpp_identity = "SIM-E2E-CP-001"
        charger.vendor = "EsLatin"
        charger.model = "Scenario Simulator"
        charger.serial_number = "SIM-E2E-SERIAL-001"
        charger.firmware_version = "1.0.0"
        charger.max_power_kw = 7.0
        charger.is_active = True
        # The primary simulator is the local app happy-path fixture. Keep it
        # commercially commissioned so the QR flow can reach OCPP testing.
        charger.commissioning_status = "commissioned"
        charger.commissioned_at = charger.commissioned_at or now
        db.add(charger)

        other_charger = db.get(
            ChargePoint, ids["other-charge-point"]
        ) or ChargePoint(id=ids["other-charge-point"])
        other_charger.tenant_id = tenant.id
        other_charger.site_id = site.id
        other_charger.ocpp_identity = "SIM-E2E-CP-OTHER-001"
        other_charger.vendor = "EsLatin"
        other_charger.model = "Scenario Simulator"
        other_charger.serial_number = "SIM-E2E-SERIAL-OTHER-001"
        other_charger.firmware_version = "1.0.0"
        other_charger.max_power_kw = 7.0
        other_charger.is_active = True
        db.add(other_charger)

        tenant_b_charger = db.get(
            ChargePoint, ids["tenant-b-charge-point"]
        ) or ChargePoint(id=ids["tenant-b-charge-point"])
        tenant_b_charger.tenant_id = tenant_b.id
        tenant_b_charger.site_id = tenant_b_site.id
        tenant_b_charger.ocpp_identity = "SIM-E2E-TENANT-B-CP-001"
        tenant_b_charger.vendor = "EsLatin"
        tenant_b_charger.model = "Scenario Simulator"
        tenant_b_charger.serial_number = "SIM-E2E-TENANT-B-SERIAL-001"
        tenant_b_charger.firmware_version = "1.0.0"
        tenant_b_charger.max_power_kw = 7.0
        tenant_b_charger.is_active = True
        db.add(tenant_b_charger)

        evse = db.get(EVSE, ids["evse"]) or EVSE(id=ids["evse"])
        evse.tenant_id = tenant.id
        evse.charge_point_id = charger.id
        evse.evse_id = 1
        evse.connector_type = "Type2"
        evse.max_power_kw = 7.0
        evse.physical_reference = "A-01"
        db.add(evse)

        other_evse = db.get(EVSE, ids["other-evse"]) or EVSE(id=ids["other-evse"])
        other_evse.tenant_id = tenant.id
        other_evse.charge_point_id = other_charger.id
        other_evse.evse_id = 1
        other_evse.connector_type = "Type2"
        other_evse.max_power_kw = 7.0
        other_evse.physical_reference = "B-01"
        db.add(other_evse)

        tenant_b_evse = db.get(
            EVSE, ids["tenant-b-evse"]
        ) or EVSE(id=ids["tenant-b-evse"])
        tenant_b_evse.tenant_id = tenant_b.id
        tenant_b_evse.charge_point_id = tenant_b_charger.id
        tenant_b_evse.evse_id = 1
        tenant_b_evse.connector_type = "Type2"
        tenant_b_evse.max_power_kw = 7.0
        tenant_b_evse.physical_reference = "C-01"
        db.add(tenant_b_evse)

        evse_status = db.get(EVSEStatus, ids["evse-status"]) or EVSEStatus(
            id=ids["evse-status"]
        )
        evse_status.tenant_id = tenant.id
        evse_status.charge_point_id = charger.id
        evse_status.evse_id = evse.id
        evse_status.status = "Offline"
        evse_status.last_seen = now
        db.add(evse_status)

        other_evse_status = db.get(
            EVSEStatus, ids["other-evse-status"]
        ) or EVSEStatus(id=ids["other-evse-status"])
        other_evse_status.tenant_id = tenant.id
        other_evse_status.charge_point_id = other_charger.id
        other_evse_status.evse_id = other_evse.id
        other_evse_status.status = "Available"
        other_evse_status.last_seen = now
        db.add(other_evse_status)

        tenant_b_evse_status = db.get(
            EVSEStatus, ids["tenant-b-evse-status"]
        ) or EVSEStatus(id=ids["tenant-b-evse-status"])
        tenant_b_evse_status.tenant_id = tenant_b.id
        tenant_b_evse_status.charge_point_id = tenant_b_charger.id
        tenant_b_evse_status.evse_id = tenant_b_evse.id
        tenant_b_evse_status.status = "Available"
        tenant_b_evse_status.last_seen = now
        db.add(tenant_b_evse_status)

        tariff = db.get(Tariff, ids["tariff"]) or Tariff(id=ids["tariff"])
        tariff.tenant_id = tenant.id
        tariff.site_id = site.id
        tariff.charge_point_id = None
        tariff.name = "SIM E2E Fixed Tariff"
        tariff.base_price_per_kwh = Decimal("2700.00")
        tariff.service_fee = Decimal("0.00")
        tariff.valid_from = now
        tariff.valid_until = None
        tariff.is_active = True
        db.add(tariff)

        qr = db.get(QrToken, ids["qr"]) or QrToken(id=ids["qr"])
        qr.token = qr_token
        qr.operator_tenant_id = tenant.id
        qr.charge_point_id = charger.id
        qr.connector_id = 1
        qr.revoked_at = None
        db.add(qr)

        other_qr = db.get(QrToken, ids["other-qr"]) or QrToken(id=ids["other-qr"])
        other_qr.token = other_qr_token
        other_qr.operator_tenant_id = tenant.id
        other_qr.charge_point_id = other_charger.id
        other_qr.connector_id = 1
        other_qr.revoked_at = None
        db.add(other_qr)

        tenant_b_qr = db.get(
            QrToken, ids["tenant-b-qr"]
        ) or QrToken(id=ids["tenant-b-qr"])
        tenant_b_qr.token = tenant_b_qr_token
        tenant_b_qr.operator_tenant_id = tenant_b.id
        tenant_b_qr.charge_point_id = tenant_b_charger.id
        tenant_b_qr.connector_id = 1
        tenant_b_qr.revoked_at = None
        db.add(tenant_b_qr)

        charging_payment_order = db.get(
            PaymentOrder, ids["charging-payment-order"]
        ) or PaymentOrder(id=ids["charging-payment-order"])
        charging_payment_order.app_user_id = other_app_user.id
        charging_payment_order.type = "charging"
        charging_payment_order.amount = Decimal("5000.00")
        charging_payment_order.currency = "COP"
        charging_payment_order.payment_provider = "fake"
        charging_payment_order.idempotency_key = "sim-e2e-fake-charging-payment"
        charging_payment_order.status = "created"
        charging_payment_order.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
        charging_payment_order.order_metadata = {
            "session_id": str(ids["ownership-session"]),
            "scenario": "p0-ownership-fake-payment",
        }
        db.add(charging_payment_order)

        ownership_session = db.get(
            ChargingSession, ids["ownership-session"]
        ) or ChargingSession(id=ids["ownership-session"])
        ownership_session.tenant_id = tenant.id
        ownership_session.evse_id = other_evse.id
        ownership_session.charge_point_id = other_charger.id
        ownership_session.transaction_id = 900001
        ownership_session.id_tag = "SIM-E2E-OTHER-APP"
        ownership_session.user_id = str(other_app_user.id)
        ownership_session.app_user_id = other_app_user.id
        ownership_session.start_time = now
        ownership_session.end_time = now
        ownership_session.meter_start = 0
        ownership_session.meter_stop = 0
        # Ownership/payment fixtures are historical facts. Seed data must not
        # occupy a connector or leak an active session into another scenario.
        ownership_session.status = "completed"
        ownership_session.payment_status = "unpaid"
        ownership_session.payment_order_id = charging_payment_order.id
        db.add(ownership_session)

        top_up_payment_order = db.get(
            PaymentOrder, ids["top-up-payment-order"]
        ) or PaymentOrder(id=ids["top-up-payment-order"])
        top_up_payment_order.app_user_id = low_balance_user.id
        top_up_payment_order.type = "top_up"
        top_up_payment_order.amount = Decimal("10000.00")
        top_up_payment_order.currency = "COP"
        top_up_payment_order.payment_provider = "fake"
        top_up_payment_order.idempotency_key = "sim-e2e-fake-top-up-payment"
        top_up_payment_order.status = "created"
        top_up_payment_order.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
        top_up_payment_order.order_metadata = {"scenario": "p0-fake-payment-ledger"}
        db.add(top_up_payment_order)

        fault_alert = db.get(Alert, ids["fault-alert"]) or Alert(id=ids["fault-alert"])
        fault_alert.tenant_id = tenant.id
        fault_alert.charge_point_id = charger.id
        fault_alert.evse_id = evse.id
        fault_alert.alert_type = "faulted"
        fault_alert.dedupe_key = f"faulted:{charger.id}:{evse.id}"
        fault_alert.severity = "critical"
        fault_alert.status = "resolved"
        fault_alert.title = "SIM E2E deterministic fault alert"
        fault_alert.description = "Reopened by the P0 fault scenario"
        fault_alert.alert_metadata = {"scenario": "p0-fault-alert"}
        fault_alert.resolved_at = now
        db.add(fault_alert)

        top_up = db.get(AppWalletTransaction, ids["wallet-top-up"]) or AppWalletTransaction(
            id=ids["wallet-top-up"]
        )
        top_up.transaction_number = "wallet_sim_e2e_seed"
        top_up.app_user_id = app_user.id
        top_up.operator_tenant_id = tenant.id
        top_up.charge_point_id = charger.id
        top_up.type = "top_up"
        top_up.amount = Decimal("100000.00")
        top_up.description = "SIM-E2E deterministic opening balance"
        top_up.idempotency_key = "sim-e2e-seed-opening-balance"
        top_up.adjusted_by_admin_id = admin.id
        db.add(top_up)

        db.commit()
        print(json.dumps({
            "schema_version": "1.1",
            "environment": environment,
            "tenant_id": str(tenant.id),
            "admin": {"id": str(admin.id), "username": admin.username, "email": admin.email},
            "app_user": {"id": str(app_user.id), "email": app_user.email, "balance": str(app_user.balance)},
            "site": {"id": str(site.id), "site_code": site.site_code},
            "charge_point": {"id": str(charger.id), "ocpp_identity": charger.ocpp_identity},
            "evse": {"id": str(evse.id), "connector_id": evse.evse_id},
            "tariff": {"id": str(tariff.id), "price_per_kwh": str(tariff.base_price_per_kwh)},
            "qr": {"id": str(qr.id), "payload": f"qr:{qr.token}"},
            "fixtures": {
                "tenants": {
                    "tenant_a": {"id": str(tenant.id), "domain": tenant.domain},
                    "tenant_b": {"id": str(tenant_b.id), "domain": tenant_b.domain},
                },
                "admins": {
                    "operator": {
                        "id": str(admin.id), "username": admin.username, "email": admin.email,
                        "tenant_id": str(tenant.id),
                    },
                    "readonly": {
                        "id": str(readonly_admin.id), "username": readonly_admin.username,
                        "email": readonly_admin.email, "tenant_id": str(tenant.id),
                        "role_id": str(readonly_role.id),
                    },
                },
                "app_users": {
                    "funded": {
                        "id": str(app_user.id), "email": app_user.email,
                        "balance": str(app_user.balance),
                    },
                    "low_balance": {
                        "id": str(low_balance_user.id), "email": low_balance_user.email,
                        "balance": str(low_balance_user.balance),
                    },
                    "other": {
                        "id": str(other_app_user.id), "email": other_app_user.email,
                        "balance": str(other_app_user.balance),
                    },
                },
                "charge_points": {
                    "primary": {"id": str(charger.id), "ocpp_identity": charger.ocpp_identity},
                    "other": {
                        "id": str(other_charger.id),
                        "ocpp_identity": other_charger.ocpp_identity,
                    },
                    "tenant_b": {
                        "id": str(tenant_b_charger.id),
                        "ocpp_identity": tenant_b_charger.ocpp_identity,
                    },
                },
                "qrs": {
                    "primary": {"id": str(qr.id), "payload": f"qr:{qr.token}"},
                    "other": {"id": str(other_qr.id), "payload": f"qr:{other_qr.token}"},
                    "tenant_b": {
                        "id": str(tenant_b_qr.id), "payload": f"qr:{tenant_b_qr.token}",
                    },
                },
                "ownership_session": {
                    "id": str(ownership_session.id),
                    "transaction_id": ownership_session.transaction_id,
                    "app_user_id": str(other_app_user.id),
                    "payment_order_id": str(charging_payment_order.id),
                },
                "fake_top_up_order": {
                    "id": str(top_up_payment_order.id),
                    "app_user_id": str(low_balance_user.id),
                    "amount": str(top_up_payment_order.amount),
                },
                "fault_alert": {
                    "id": str(fault_alert.id), "dedupe_key": fault_alert.dedupe_key,
                },
            },
        }, sort_keys=True))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
