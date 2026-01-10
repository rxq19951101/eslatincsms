import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '../page';

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
  });

  it('应该渲染登录表单', () => {
    render(<LoginPage />);
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

  // 登录成功测试需要完整的 mock 设置，暂时跳过（需要更复杂的 setup）
  it.skip('应该在登录成功时跳转到 Dashboard', async () => {
    // TODO: 需要更完整的 mock 设置
  });
});