"""Admin site list/detail must use the same selected-tenant scope."""

import uuid

from app.database.models import Site, Tenant


def test_super_admin_selected_tenant_filters_site_list(
    admin_client,
    db_session,
    sample_site,
):
    selected_tenant_id = uuid.UUID(admin_client.headers['X-Tenant-Id'])
    assert sample_site.tenant_id == selected_tenant_id

    other_tenant = Tenant(id=uuid.uuid4(), name='Other tenant', status='active')
    other_site = Site(
        id=uuid.uuid4(),
        site_code='SITE-OTHER-TENANT',
        tenant_id=other_tenant.id,
        name='Other tenant site',
        address='Calle 200 # 1-10, Bogota',
        latitude=4.7,
        longitude=-74.0,
        is_active=True,
    )
    db_session.add_all([other_tenant, other_site])
    db_session.commit()

    response = admin_client.get('/api/v1/sites')

    assert response.status_code == 200
    returned_ids = {item['id'] for item in response.json()}
    assert str(sample_site.id) in returned_ids
    assert str(other_site.id) not in returned_ids
