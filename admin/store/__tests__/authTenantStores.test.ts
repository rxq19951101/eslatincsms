import { beforeEach, describe, expect, it } from 'vitest';
import { STORAGE_KEYS } from '@/lib/constants';
import { useAuthStore } from '../authStore';
import { useTenantStore } from '../tenantStore';
import type { AdminUser, Tenant } from '@/types';

const tenant: Tenant = { id: 'shared-tenant', name: 'Shared tenant', is_primary: true };

const createUser = (id: string): AdminUser => ({
  id,
  username: id,
  email: `${id}@example.com`,
  is_super_admin: false,
  default_tenant_id: tenant.id,
  tenant_list: [tenant],
});

describe('auth and tenant stores', () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
    useAuthStore.getState().setHasHydrated(true);
  });

  it('切换管理员账号时清除内存和持久化租户，即使两个账号共享租户', () => {
    useAuthStore.getState().setUser(createUser('admin-a'));
    useTenantStore.getState().setCurrentTenant(tenant, 'admin-a');

    useAuthStore.getState().setUser(createUser('admin-b'));

    expect(useTenantStore.getState().currentTenant).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBeNull();
  });

  it('登出同时清除 token、用户、租户内存和租户 localStorage', () => {
    useAuthStore.getState().setUser(createUser('admin-a'));
    useTenantStore.getState().setCurrentTenant(tenant, 'admin-a');
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, 'access-token');
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, 'refresh-token');

    useAuthStore.getState().logout();

    expect(useAuthStore.getState().user).toBeNull();
    expect(useTenantStore.getState().currentTenant).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBeNull();
  });
});
