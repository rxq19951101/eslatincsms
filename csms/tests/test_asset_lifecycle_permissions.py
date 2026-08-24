"""Permission and tenant-boundary QA for asset lifecycle endpoints."""

from uuid import uuid4

from app.core.auth import create_access_token, get_password_hash
from app.database.models import (
    AdminUser,
    Role,
    Tenant,
    TenantMembership,
    TenantMembershipRole,
)


def _authorize_tenant_admin(client, db_session, tenant_id, permissions, suffix):
    admin = AdminUser(
        id=uuid4(),
        username=f"lifecycle-{suffix}",
        email=f"lifecycle-{suffix}@example.com",
        password_hash=get_password_hash("test-password"),
        is_active=True,
        is_super_admin=False,
    )
    membership = TenantMembership(
        tenant_id=tenant_id,
        admin_user_id=admin.id,
        status="active",
        is_primary=True,
    )
    role = Role(
        id=uuid4(),
        tenant_id=tenant_id,
        name=f"lifecycle-role-{suffix}",
        permissions=permissions,
        scope="tenant",
    )
    db_session.add_all([admin, membership, role])
    db_session.flush()
    db_session.add(
        TenantMembershipRole(membership_id=membership.id, role_id=role.id)
    )
    db_session.commit()

    token = create_access_token(
        {
            "user_id": str(admin.id),
            "user_type": "admin",
            "aud": "admin",
        }
    )
    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(tenant_id),
        }
    )
    return admin


def test_lifecycle_reads_and_writes_require_explicit_permissions(
    client,
    db_session,
    sample_site,
    sample_charge_point,
):
    _authorize_tenant_admin(
        client,
        db_session,
        sample_site.tenant_id,
        permissions=[],
        suffix="no-permissions",
    )

    assert client.get(
        f"/api/v1/sites/{sample_site.id}/archive-preflight"
    ).status_code == 403
    assert client.get(
        f"/api/v1/chargers/{sample_charge_point.id}/retirement-preflight"
    ).status_code == 403
    assert client.get("/api/v1/asset-archive/sites").status_code == 403
    assert client.get("/api/v1/asset-archive/chargers").status_code == 403

    _authorize_tenant_admin(
        client,
        db_session,
        sample_site.tenant_id,
        permissions=["sites.read", "chargers.read"],
        suffix="read-only",
    )

    assert client.get(
        f"/api/v1/sites/{sample_site.id}/archive-preflight"
    ).status_code == 200
    assert client.get(
        f"/api/v1/chargers/{sample_charge_point.id}/retirement-preflight"
    ).status_code == 200
    assert client.get("/api/v1/asset-archive/sites").status_code == 200
    assert client.get("/api/v1/asset-archive/chargers").status_code == 200
    assert client.post(
        f"/api/v1/sites/{sample_site.id}/archive",
        json={"reason": "Read-only user must not archive"},
    ).status_code == 403
    assert client.post(
        f"/api/v1/chargers/{sample_charge_point.id}/retire",
        json={"reason": "Read-only user must not retire"},
    ).status_code == 403

    db_session.refresh(sample_site)
    db_session.refresh(sample_charge_point)
    assert sample_site.is_active is True
    assert sample_charge_point.is_active is True


def test_lifecycle_endpoints_reject_cross_tenant_assets_without_mutation(
    client,
    db_session,
    sample_site,
    sample_charge_point,
):
    other_tenant = Tenant(id=uuid4(), name="Lifecycle other tenant", status="active")
    db_session.add(other_tenant)
    db_session.commit()
    _authorize_tenant_admin(
        client,
        db_session,
        other_tenant.id,
        permissions=[
            "sites.read",
            "sites.write",
            "chargers.read",
            "chargers.write",
        ],
        suffix="other-tenant",
    )

    responses = [
        client.get(f"/api/v1/sites/{sample_site.id}/archive-preflight"),
        client.post(
            f"/api/v1/sites/{sample_site.id}/archive",
            json={"reason": "Cross-tenant archive attempt"},
        ),
        client.get(
            f"/api/v1/chargers/{sample_charge_point.id}/retirement-preflight"
        ),
        client.post(
            f"/api/v1/chargers/{sample_charge_point.id}/retire",
            json={"reason": "Cross-tenant retirement attempt"},
        ),
    ]
    assert [response.status_code for response in responses] == [403, 403, 403, 403]

    db_session.refresh(sample_site)
    db_session.refresh(sample_charge_point)
    assert sample_site.is_active is True
    assert sample_charge_point.is_active is True
