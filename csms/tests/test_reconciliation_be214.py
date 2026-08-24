from datetime import date
from uuid import uuid4

import pytest

from app.database.models import AdminUser
from app.services.reconciliation import (
    ReconciliationExportConsumed,
    ReconciliationExportExpired,
    ReconciliationExportFailed,
    ReconciliationExportStateError,
    ReconciliationService,
)


def _export(db, *, status="queued", content=None, tenant_id=None):
    service = ReconciliationService()
    admin = db.query(AdminUser).filter(AdminUser.is_super_admin.is_(True)).first()
    if admin is None:
        admin = AdminUser(
            username=f"be214-{uuid4().hex[:8]}",
            email=f"be214-{uuid4().hex[:8]}@example.test",
            password_hash="test-only",
            is_super_admin=True,
        )
        db.add(admin)
        db.flush()
    run = service.create_run(
        db,
        provider="mercadopago",
        provider_account_ref=f"be214-{uuid4().hex}",
        business_date=date(2026, 8, 17),
        source_checksum=f"be214-{uuid4().hex}",
        actor=admin,
        tenant_id=tenant_id,
    )
    export = service.create_export(
        db,
        actor=admin,
        run_id=run.id,
        filters={"status": []},
        idempotency_key=f"be214-{uuid4().hex}",
        tenant_id=tenant_id,
    )
    export.status = status
    export.content = content
    if status == "ready":
        export.row_count = 1
    db.commit()
    db.refresh(export)
    return service, admin, export


@pytest.mark.parametrize(
    ("status", "error_type", "code", "http_status"),
    [
        ("failed", ReconciliationExportFailed, "EXPORT_FAILED", 409),
        ("expired", ReconciliationExportExpired, "EXPORT_EXPIRED", 410),
        ("downloaded", ReconciliationExportConsumed, "EXPORT_CONSUMED", 410),
        ("queued", ReconciliationExportStateError, "EXPORT_NOT_READY", 409),
    ],
)
def test_be214_export_terminal_and_not_ready_errors(db_session, status, error_type, code, http_status):
    service, admin, export = _export(db_session, status=status, content="header\nvalue\n")

    with pytest.raises(error_type) as caught:
        service.download_export(db_session, actor=admin, export_id=export.id)

    assert caught.value.code == code
    assert caught.value.status_code == http_status


def test_be214_ready_download_has_safe_filename_content_type_and_audit_reference(
    admin_client, db_session, sample_tenant
):
    _, _, export = _export(
        db_session, status="ready", content="header\nvalue\n", tenant_id=sample_tenant.id
    )

    response = admin_client.get(
        f"/api/v1/admin/reconciliation/exports/{export.id}/download"
        f"?tenant_scope={sample_tenant.id}"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="reconciliation-{export.id}.csv"'
    )
    assert response.headers["x-audit-reference"] == export.audit_reference
    assert response.text == "header\nvalue\n"


@pytest.mark.parametrize(
    ("status", "expected_code", "expected_status"),
    [
        ("failed", "EXPORT_FAILED", 409),
        ("expired", "EXPORT_EXPIRED", 410),
        ("downloaded", "EXPORT_CONSUMED", 410),
        ("queued", "EXPORT_NOT_READY", 409),
    ],
)
def test_be214_download_error_boundary_returns_canonical_codes(
    admin_client, db_session, sample_tenant, status, expected_code, expected_status
):
    _, _, export = _export(
        db_session, status=status, content="header\nvalue\n", tenant_id=sample_tenant.id
    )

    response = admin_client.get(
        f"/api/v1/admin/reconciliation/exports/{export.id}/download"
        f"?tenant_scope={sample_tenant.id}"
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
