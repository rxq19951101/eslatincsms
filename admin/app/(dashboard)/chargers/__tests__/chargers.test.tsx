import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChargersPage from '../page';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

// Mock SWR
const mockMutate = vi.fn();
vi.mock('swr', () => ({
  default: (key: string, fetcher: Function) => {
    if (key.includes('/chargers')) {
      return {
        data: [
          {
            id: 'CP001',
            vendor: 'Tesla',
            model: 'Supercharger V3',
            status: 'Available',
            last_seen: new Date().toISOString(),
            location: {
              latitude: 39.9042,
              longitude: 116.4074,
              address: '北京市朝阳区',
            },
            price_per_kwh: 1.5,
            is_configured: true,
            has_location: true,
            has_pricing: true,
          },
          {
            id: 'CP002',
            vendor: 'ABB',
            model: 'Terra AC',
            status: 'Charging',
            last_seen: new Date().toISOString(),
            location: {
              latitude: 39.9042,
              longitude: 116.4074,
              address: '北京市海淀区',
            },
            price_per_kwh: 2.0,
            is_configured: true,
            has_location: true,
            has_pricing: true,
          },
        ],
        error: null,
        isLoading: false,
        mutate: mockMutate,
      };
    }
    return { data: null, error: null, isLoading: false, mutate: mockMutate };
  },
}));

describe('ChargersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('应该渲染充电桩列表', async () => {
    render(<ChargersPage />);
    
    await waitFor(() => {
      expect(screen.getByText('CP001')).toBeInTheDocument();
      expect(screen.getByText('CP002')).toBeInTheDocument();
    });
  });

  it('应该支持搜索功能', async () => {
    const user = userEvent.setup();
    render(<ChargersPage />);
    
    await waitFor(() => {
      expect(screen.getByText('CP001')).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // 查找搜索输入框（使用实际的 placeholder）
    const searchInput = screen.getByPlaceholderText(/搜索充电桩/i);
    await user.type(searchInput, 'Tesla');
    
    // 等待过滤生效
    await waitFor(() => {
      expect(screen.getByText('CP001')).toBeInTheDocument();
      // CP002 的 vendor 是 'ABB'，应该被过滤掉
      expect(screen.queryByText('CP002')).not.toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('应该支持状态过滤', async () => {
    render(<ChargersPage />);
    
    await waitFor(() => {
      expect(screen.getByText('CP001')).toBeInTheDocument();
      expect(screen.getByText('CP002')).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // 测试状态过滤器存在（查找 Select 组件）
    const statusFilter = screen.getByText('全部状态');
    expect(statusFilter).toBeInTheDocument();
  });

  // 加载状态测试需要单独的文件，因为 vi.mock 在同一个文件中不能动态改变
  it.skip('应该显示加载状态', () => {
    // 这个测试需要单独的测试文件或不同的 mock 设置
  });
});