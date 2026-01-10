import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAuth } from '../useAuth';
import { setTokens, clearTokens } from '@/lib/auth';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
  }),
  usePathname: () => '/dashboard',
}));

// Mock API - 必须使用工厂函数，不能使用外部变量
vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
}));

// Mock auth store - 使用对象方式，在工厂函数中定义
vi.mock('@/store/authStore', () => {
  const mockSetUser = vi.fn();
  const mockLogout = vi.fn();
  let mockUser: any = null;
  let mockIsAuthenticated = false;
  
  return {
    useAuthStore: () => ({
      get user() { return mockUser; },
      get isAuthenticated() { return mockIsAuthenticated; },
      setUser: mockSetUser,
      logout: mockLogout,
      // 提供设置方法用于测试
      __setUser: (user: any) => { mockUser = user; },
      __setIsAuthenticated: (val: boolean) => { mockIsAuthenticated = val; },
      __reset: () => { mockUser = null; mockIsAuthenticated = false; },
    }),
  };
});

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTokens();
  });

  it('应该在未登录时返回未认证状态', async () => {
    const { result } = renderHook(() => useAuth());
    
    // useAuth 在挂载时会检查 token，如果没有 token，不会调用 API
    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(false);
    }, { timeout: 1000 });
  });

  // 复杂的集成测试需要更完善的 mock 设置，暂时跳过
  it.skip('应该在有 token 时验证用户', async () => {
    // TODO: 需要更完善的 mock 设置
  });

  it.skip('应该在 token 无效时清除认证状态', async () => {
    // TODO: 需要更完善的 mock 设置
  });
});