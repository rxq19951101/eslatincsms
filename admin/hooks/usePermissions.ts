import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';

type PermissionsResponse = { permissions: string[] };

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function hasPermission(permissions: string[] | undefined | null, required: string): boolean {
  if (!permissions || permissions.length === 0) return false;
  if (permissions.includes('*')) return true;
  if (permissions.includes('tenant.*')) return true;
  for (const p of permissions) {
    if (p === required) return true;
    if (p.includes('*')) {
      const re = new RegExp(`^${escapeRegex(p).replace(/\\\*/g, '.*')}$`);
      if (re.test(required)) return true;
    }
  }
  return false;
}

export function usePermissions() {
  const user = useAuthStore((s) => s.user);
  const currentTenant = useTenantStore((s) => s.currentTenant);

  const tenantKey = user?.is_super_admin ? 'super' : currentTenant?.id || 'none';
  const shouldFetch = !!user && (user.is_super_admin || !!currentTenant?.id);

  const { data, error, isLoading, mutate } = useSWR<PermissionsResponse>(
    shouldFetch ? [API_ENDPOINTS.AUTH_ME_PERMISSIONS, tenantKey] : null,
    async () => apiGet<PermissionsResponse>(API_ENDPOINTS.AUTH_ME_PERMISSIONS),
    { revalidateOnFocus: false }
  );

  const permissions = data?.permissions || [];

  return {
    permissions,
    isLoading,
    error,
    refresh: mutate,
  };
}

