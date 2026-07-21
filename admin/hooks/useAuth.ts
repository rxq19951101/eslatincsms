import { useEffect, useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { getAccessToken, redirectToLogin } from '@/lib/auth';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { AdminUser } from '@/types';
import { useTenantStore } from '@/store/tenantStore';
import { getDefaultTenant, getTenantId } from '@/lib/tenant';
import type { TenantRecord } from '@/types';

/**
 * 认证 Hook
 * 负责页面启动时验证 token 有效性
 */
export function useAuth() {
  const { user, hasHydrated, setUser, logout } = useAuthStore();
  const { currentTenant, setCurrentTenant, clearTenant } = useTenantStore();
  const [isReady, setIsReady] = useState(false);

  // 页面启动时验证 token
  useEffect(() => {
    if (!hasHydrated) return;

    let cancelled = false;

    const verifyAuth = async () => {
      // 跳过登录页面
      if (typeof window !== 'undefined' && window.location.pathname === '/login') {
        if (!cancelled) setIsReady(true);
        return;
      }

      const accessToken = getAccessToken();
      
      if (!accessToken) {
        if (user) logout();
        if (!cancelled) setIsReady(true);
        return;
      }

      // 如果已有用户信息，不重复验证
      if (user) {
        if (!cancelled) setIsReady(true);
        return;
      }

      try {
        // 验证 token 有效性
        const userData = await apiGet<AdminUser>(API_ENDPOINTS.AUTH_ME, {
          skipTenantId: true, // 认证接口不需要 tenant_id
        });
        
        if (!cancelled) setUser(userData);
      } catch (error) {
        // 验证失败，清除 token（但不在这里跳转，由 useRequireAuth 处理）
        console.error('Token verification failed:', error);
        if (!cancelled) logout();
      } finally {
        if (!cancelled) setIsReady(true);
      }
    };

    // 只在客户端执行
    if (typeof window !== 'undefined') {
      verifyAuth();
    }

    return () => {
      cancelled = true;
    };
  }, [hasHydrated, user, setUser, logout]);

  // 当 user 恢复/更新后，自动初始化当前租户（用于右上角展示）
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!hasHydrated || !user) return;
    let cancelled = false;

    const initTenant = async () => {
      // super_admin：仍然允许“可选租户”
      // - 不选租户：用于全局聚合类接口
      // - 选中租户：用于站点/桩等租户资产的写操作（需要 X-Tenant-Id）
      if (user.is_super_admin) {
        if (currentTenant) return;
        const tid = getTenantId(user);
        if (!tid) return;
        try {
          const tenants = await apiGet<TenantRecord[]>(API_ENDPOINTS.TENANTS, { skipTenantId: true });
          if (cancelled || useAuthStore.getState().user?.id !== user.id) return;
          const tenant = tenants.find((item) => item.id === tid);
          if (tenant) {
            setCurrentTenant({ id: tenant.id, name: tenant.name, is_primary: false }, user.id);
          } else {
            clearTenant();
          }
        } catch {
          // ignore: super_admin 仍可不选租户，仅写操作会在后端提示 Tenant ID required
        }
        return;
      }

      // 普通租户用户：恢复当前账号的受控选择，否则使用有效 default/primary 租户。
      if (!currentTenant) {
        const tid = getTenantId(user);
        const selected =
          (tid && user.tenant_list?.find((t) => t.id === tid)) ||
          getDefaultTenant(user);
        if (selected) setCurrentTenant(selected, user.id);
      }
    };

    initTenant();

    return () => {
      cancelled = true;
    };
  }, [hasHydrated, user, currentTenant, setCurrentTenant, clearTenant]);

  // 认证状态不要依赖 store 里单独存的 isAuthenticated（刷新后不一定能正确恢复），而是实时基于 token + user 计算
  const isAuthenticated = hasHydrated && typeof window !== 'undefined' && !!getAccessToken() && !!user;

  return {
    user,
    isAuthenticated,
    isReady,
    setUser,
    logout,
  };
}

/**
 * 路由保护 Hook
 * 用于保护需要认证的页面
 */
export function useRequireAuth() {
  const { isAuthenticated, isReady } = useAuth();

  useEffect(() => {
    // 等认证校验完成后再决定是否跳转，避免刷新时误判“未登录”导致每次都回到登录页
    if (isReady && !isAuthenticated && typeof window !== 'undefined') {
      redirectToLogin();
    }
  }, [isAuthenticated, isReady]);

  return { isAuthenticated, isReady };
}
