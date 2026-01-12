import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { getAccessToken, redirectToLogin } from '@/lib/auth';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { AdminUser } from '@/types';

/**
 * 认证 Hook
 * 负责页面启动时验证 token 有效性
 */
export function useAuth() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const [isReady, setIsReady] = useState(false);

  // 页面启动时验证 token
  useEffect(() => {
    const verifyAuth = async () => {
      // 跳过登录页面
      if (typeof window !== 'undefined' && window.location.pathname === '/login') {
        setIsReady(true);
        return;
      }

      const accessToken = getAccessToken();
      
      if (!accessToken) {
        // 没有 token：标记就绪（由 useRequireAuth 决定是否跳转）
        setIsReady(true);
        return;
      }

      // 如果已有用户信息，不重复验证
      if (user) {
        setIsReady(true);
        return;
      }

      try {
        // 验证 token 有效性
        const userData = await apiGet<AdminUser>(API_ENDPOINTS.AUTH_ME, {
          skipTenantId: true, // 认证接口不需要 tenant_id
        });
        
        setUser(userData);
      } catch (error) {
        // 验证失败，清除 token（但不在这里跳转，由 useRequireAuth 处理）
        console.error('Token verification failed:', error);
        logout();
      } finally {
        setIsReady(true);
      }
    };

    // 只在客户端执行
    if (typeof window !== 'undefined') {
      verifyAuth();
    }
  }, []); // 只在组件挂载时执行一次

  // 认证状态不要依赖 store 里单独存的 isAuthenticated（刷新后不一定能正确恢复），而是实时基于 token + user 计算
  const isAuthenticated = typeof window !== 'undefined' && !!getAccessToken() && !!user;

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
  const router = useRouter();

  useEffect(() => {
    // 等认证校验完成后再决定是否跳转，避免刷新时误判“未登录”导致每次都回到登录页
    if (isReady && !isAuthenticated && typeof window !== 'undefined') {
      redirectToLogin();
    }
  }, [isAuthenticated, isReady]);

  return { isAuthenticated, isReady };
}