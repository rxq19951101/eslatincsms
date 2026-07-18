import { describe, expect, it } from 'vitest';

import { tenantProvisionPayload, tenantProvisionResult } from '@/lib/tenant-provision';
import { tenantProvisionSchema } from '@/lib/validation';
import type { TenantProvisionResponse } from '@/types';

describe('tenant provision wire contract', () => {
  const validatedForm = tenantProvisionSchema.parse({
    name: '  EsLatin Colombia  ',
    domain: 'co.eslatin.example',
    subscription_plan: 'pro',
    max_charge_points: 50,
    max_users: 500,
    admin_username: 'tenant_admin',
    admin_email: 'admin@example.com',
    admin_full_name: '  Tenant Admin  ',
    admin_password: 'temporary-pass-123',
  });

  it('sends the frozen nested tenant and admin payload', () => {
    expect(tenantProvisionPayload(validatedForm)).toEqual({
      tenant: {
        name: 'EsLatin Colombia',
        domain: 'co.eslatin.example',
        subscription_plan: 'pro',
        max_charge_points: 50,
        max_users: 500,
        settings: {},
      },
      admin: {
        username: 'tenant_admin',
        email: 'admin@example.com',
        password: 'temporary-pass-123',
        full_name: 'Tenant Admin',
      },
    });
  });

  it('accepts tenant, full admin and membership_id while keeping the password local', () => {
    const response: TenantProvisionResponse = {
      tenant: {
        id: 'tenant-uuid',
        name: 'EsLatin Colombia',
        domain: 'co.eslatin.example',
        status: 'active',
        subscription_plan: 'pro',
        max_charge_points: 50,
        max_users: 500,
        settings: {},
        created_at: '2026-07-17T00:00:00Z',
        updated_at: '2026-07-17T00:00:00Z',
      },
      admin: {
        id: 'admin-uuid',
        username: 'tenant_admin',
        email: 'admin@example.com',
        full_name: 'Tenant Admin',
        is_active: true,
        is_super_admin: false,
        last_login_at: null,
        created_at: '2026-07-17T00:00:00Z',
        updated_at: '2026-07-17T00:00:00Z',
      },
      membership_id: 'membership-uuid',
    };

    expect(response.admin).not.toHaveProperty('password');
    expect(tenantProvisionResult(response, validatedForm.admin_password)).toEqual({
      ...response,
      temporary_password: 'temporary-pass-123',
    });
  });
});
