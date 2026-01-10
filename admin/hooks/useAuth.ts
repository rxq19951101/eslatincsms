import { useEffect } from 'react';
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
  const { user, setUser, logout, isAuthenticated } = useAuthStore();

  // 页面启动时验证 token
  useEffect(() => {
    const verifyAuth = async () => {
      // 跳过登录页面
      if (typeof window !== 'undefined' && window.location.pathname === '/login') {
        return;
      }

      const accessToken = getAccessToken();
      
      if (!accessToken) {
        // 没有 token，但不在这里跳转（由 useRequireAuth 处理）
        return;
      }

      // 如果已有用户信息，不重复验证
      if (user) {
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
      }
    };

    // 只在客户端执行
    if (typeof window !== 'undefined') {
      verifyAuth();
    }
  }, []); // 只在组件挂载时执行一次

  return {
    user,
    isAuthenticated: isAuthenticated && !!user,
    setUser,
    logout,
  };
}

/**
 * 路由保护 Hook
 * 用于保护需要认证的页面
 */
export function useRequireAuth() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated && typeof window !== 'undefined') {
      redirectToLogin();
    }
  }, [isAuthenticated]);

  return { isAuthenticated };
}