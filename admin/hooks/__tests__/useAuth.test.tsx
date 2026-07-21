import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '../useAuth';
import { clearTokens, setTokens } from '@/lib/auth';
import { apiGet } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import type { AdminUser } from '@/types';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
}));

const user: AdminUser = {
  id: 'admin-id',
  username: 'admin',
  email: 'admin@example.com',
  is_super_admin: false,
  default_tenant_id: 'tenant-id',
  tenant_list: [{ id: 'tenant-id', name: 'Tenant', is_primary: true }],
};

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTokens();
    useAuthStore.getState().logout();
    useAuthStore.getState().setHasHydrated(true);
    useTenantStore.getState().clearTenant();
  });

  it('未登录时在 hydration 完成后返回未认证状态', async () => {
    const { result } = renderHook(() => useAuth());

    await waitFor(() => expect(result.current.isReady).toBe(true));
    expect(result.current.isAuthenticated).toBe(false);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it('hydration 未完成时不判定未登录，完成后恢复持久化认证', async () => {
    setTokens('access-token', 'refresh-token');
    useAuthStore.getState().setUser(user);
    useAuthStore.getState().setHasHydrated(false);

    const { result } = renderHook(() => useAuth());

    expect(result.current.isReady).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);

    act(() => useAuthStore.getState().setHasHydrated(true));

    await waitFor(() => expect(result.current.isReady).toBe(true));
    expect(result.current.isAuthenticated).toBe(true);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it('有 token 但没有持久化用户时通过 /me 恢复认证', async () => {
    setTokens('access-token', 'refresh-token');
    vi.mocked(apiGet).mockResolvedValueOnce(user);

    const { result } = renderHook(() => useAuth());

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
    expect(apiGet).toHaveBeenCalledWith('/api/v1/admin/auth/me', { skipTenantId: true });
  });
});
