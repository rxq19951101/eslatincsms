import uuid

import pytest

from app.database.models import Tenant
from app.services.asset_lifecycle_service import (
    CHARGER_RESTORE_ACTION,
    CHARGER_RETIRE_ACTION,
    SITE_ARCHIVE_ACTION,
    LifecycleReasonError,
    add_lifecycle_audit,
    apply_charge_point_restored_state,
    apply_charge_point_retired_state,
    apply_site_archived_state,
    apply_site_restored_state,
    charge_point_lifecycle_status,
    latest_lifecycle_audit,
    normalize_lifecycle_reason,
    site_lifecycle_status,
)


def test_test_phase_state_mapping_uses_existing_columns(
    sample_site,
    sample_charge_point,
):
    sample_charge_point.commissioning_status = "commissioned"
    sample_charge_point.ocpp_auth_secret_hash = "old-secret-hash"

    assert site_lifecycle_status(sample_site) == "active"
    assert charge_point_lifecycle_status(sample_charge_point) == "active"

    apply_site_archived_state(sample_site)
    apply_charge_point_retired_state(sample_charge_point)

    assert site_lifecycle_status(sample_site) == "archived"
    assert charge_point_lifecycle_status(sample_charge_point) == "retired"
    assert sample_charge_point.commissioning_status == "suspended"
    assert sample_charge_point.ocpp_auth_secret_hash is None

    apply_site_restored_state(sample_site)
    apply_charge_point_restored_state(sample_charge_point)

    assert site_lifecycle_status(sample_site) == "active"
    assert charge_point_lifecycle_status(sample_charge_point) == "active"
    assert sample_charge_point.commissioning_status == "testing"


def test_inactive_legacy_charger_is_safely_treated_as_retired(sample_charge_point):
    sample_charge_point.is_active = False
    sample_charge_point.commissioning_status = "commissioned"

    assert charge_point_lifecycle_status(sample_charge_point) == "retired"


@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
def test_lifecycle_reason_validation_rejects_out_of_contract_values(reason):
    with pytest.raises(LifecycleReasonError):
        normalize_lifecycle_reason(reason)


def test_lifecycle_reason_is_trimmed():
    assert normalize_lifecycle_reason("  Site contract ended  ") == "Site contract ended"


def test_audit_is_staged_and_latest_lookup_is_tenant_scoped(
    db_session,
    sample_tenant,
    sample_charge_point,
):
    actor_id = uuid.uuid4()
    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Other lifecycle tenant",
        status="active",
    )
    db_session.add(other_tenant)
    db_session.flush()

    first = add_lifecycle_audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=actor_id,
        action=CHARGER_RETIRE_ACTION,
        resource_type="charge_point",
        resource_id=str(sample_charge_point.id),
        reason="Physical charger removed",
        before_data={"lifecycle_status": "active"},
        after_data={"lifecycle_status": "retired"},
        metadata={"source": "admin"},
    )
    second = add_lifecycle_audit(
        db_session,
        tenant_id=sample_tenant.id,
        actor_id=actor_id,
        action=CHARGER_RESTORE_ACTION,
        resource_type="charge_point",
        resource_id=str(sample_charge_point.id),
        reason="Device returned to service",
    )
    add_lifecycle_audit(
        db_session,
        tenant_id=other_tenant.id,
        actor_id=actor_id,
        action=CHARGER_RETIRE_ACTION,
        resource_type="charge_point",
        resource_id=str(sample_charge_point.id),
        reason="Other tenant action",
    )

    assert first.audit_metadata == {
        "source": "admin",
        "reason": "Physical charger removed",
    }
    assert first.created_at is not None

    latest = latest_lifecycle_audit(
        db_session,
        tenant_id=sample_tenant.id,
        resource_type="charge_point",
        resource_id=str(sample_charge_point.id),
        actions=[CHARGER_RETIRE_ACTION, CHARGER_RESTORE_ACTION],
    )
    assert latest is not None
    assert latest.id == second.id
    assert latest.audit_metadata["reason"] == "Device returned to service"

    assert latest_lifecycle_audit(
        db_session,
        tenant_id=sample_tenant.id,
        resource_type="site",
        resource_id=str(sample_charge_point.site_id),
        actions=[SITE_ARCHIVE_ACTION],
    ) is None
