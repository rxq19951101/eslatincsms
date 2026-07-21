import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '../page';
import { apiGet, apiPost } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { STORAGE_KEYS } from '@/lib/constants';
import type { AdminUser, LoginResponse } from '@/types';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

// Mock API
vi.mock('@/lib/api', () => ({
  apiPost: vi.fn(),
  apiGet: vi.fn(),
}));

// Mock auth
vi.mock('@/lib/auth', () => ({
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
}));

/**
 * 登录页面测试
 */
describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPush.mockClear();
    useAuthStore.getState().logout();
    useTenantStore.getState().clearTenant();
    vi.clearAllMocks();
  });

  it('应该渲染登录表单', () => {
    render(<LoginPage />);
    expect(screen.getByTestId('admin-login-username')).toBeInTheDocument();
    expect(screen.getByTestId('admin-login-password')).toBeInTheDocument();
    expect(screen.getByTestId('admin-login-submit')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入用户名')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument();
    expect(screen.getByText('登录')).toBeInTheDocument();
  });

  it('应该验证表单输入', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    
    const submitButton = screen.getByText('登录');
    await user.click(submitButton);
    
    // 应该显示验证错误
    await waitFor(() => {
      expect(screen.getByText('用户名不能为空')).toBeInTheDocument();
    });
  });

  it('超级管理员登录时清除前一账号租户并保持全平台视角', async () => {
    const user = userEvent.setup();
    const previousUser: AdminUser = {
      id: 'previous-admin',
      username: 'previous',
      email: 'previous@example.com',
      is_super_admin: false,
      default_tenant_id: 'shared-tenant',
      tenant_list: [{ id: 'shared-tenant', name: 'Shared', is_primary: true }],
    };
    const superAdmin: AdminUser = {
      id: 'super-admin',
      username: 'super',
      email: 'super@example.com',
      is_super_admin: true,
      tenant_list: [],
    };
    const response: LoginResponse = {
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      user: superAdmin,
    };
    useAuthStore.getState().setUser(previousUser);
    useTenantStore.getState().setCurrentTenant(previousUser.tenant_list[0], previousUser.id);
    vi.mocked(apiPost).mockResolvedValueOnce(response);
    vi.mocked(apiGet).mockResolvedValueOnce(superAdmin);

    render(<LoginPage />);
    await user.type(screen.getByTestId('admin-login-username'), 'super');
    await user.type(screen.getByTestId('admin-login-password'), 'password');
    await user.click(screen.getByTestId('admin-login-submit'));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/'));
    expect(useAuthStore.getState().user?.id).toBe(superAdmin.id);
    expect(useTenantStore.getState().currentTenant).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBeNull();
  });

  it('普通租户管理员登录时自动选择有效 default 租户', async () => {
    const user = userEvent.setup();
    const tenantAdmin: AdminUser = {
      id: 'tenant-admin',
      username: 'tenant-admin',
      email: 'tenant-admin@example.com',
      is_super_admin: false,
      default_tenant_id: 'default-tenant',
      tenant_list: [
        { id: 'primary-tenant', name: 'Primary', is_primary: true },
        { id: 'default-tenant', name: 'Default', is_primary: false },
      ],
    };
    vi.mocked(apiPost).mockResolvedValueOnce({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      user: tenantAdmin,
    });
    vi.mocked(apiGet).mockResolvedValueOnce(tenantAdmin);

    render(<LoginPage />);
    await user.type(screen.getByTestId('admin-login-username'), 'tenant-admin');
    await user.type(screen.getByTestId('admin-login-password'), 'password');
    await user.click(screen.getByTestId('admin-login-submit'));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/'));
    expect(useTenantStore.getState().currentTenant?.id).toBe('default-tenant');
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBe('default-tenant');
    expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBe(tenantAdmin.id);
  });
});
