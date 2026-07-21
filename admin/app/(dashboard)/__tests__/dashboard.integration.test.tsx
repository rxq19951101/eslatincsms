import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import DashboardPage from '../page';

// Mock SWR
vi.mock('swr', () => ({
  default: (key: string) => {
    // 模拟数据加载
    const mockData = {
      '/api/v1/dashboard/summary': {
        total_charge_points: 100,
        online_charge_points: 85,
        offline_charge_points: 14,
        faulted_charge_points: 2,
        charging_charge_points: 10,
        available_charge_points: 73,
        total_sites: 5,
        active_sites: 5,
        today_orders: 25,
        today_energy_kwh: 1250.5,
        today_revenue: 3750.75,
        total_users: 150,
        active_users_today: 30,
        critical_alerts: 1,
        warning_alerts: 5,
        info_alerts: 10,
      },
      '/api/v1/dashboard/trends?days=7': {
        energy_trend: [],
        revenue_trend: [],
        orders_trend: [],
      },
      '/api/v1/dashboard/sites?days=7&limit=200': [{
        site_id: 'site-1',
        site_name: 'Bogotá Centro',
        charge_points_count: 4,
        online_charge_points_count: 3,
        faulted_charge_points: 1,
        charging_charge_points: 1,
        available_charge_points: 2,
        orders_count: 12,
        energy_kwh: 40,
        revenue: 9876.5,
      }],
      '/api/v1/admin/configs/currency?default=COP': {
        config_key: 'currency',
        config_value: 'COP',
        tenant_id: 'tenant-1',
      },
    };
    return {
      data: mockData[key as keyof typeof mockData],
      error: null,
      isLoading: false,
    };
  },
}));

/**
 * Dashboard 页面集成测试
 * 测试页面组件与 API 的集成
 */
describe('Dashboard Page Integration', () => {
  it('应该显示 Dashboard 标题', () => {
    render(<DashboardPage />);
    expect(screen.getByText('仪表板')).toBeInTheDocument();
  });

  it('使用租户币种配置格式化收入，不显示硬编码人民币符号', () => {
    const { container } = render(<DashboardPage />);

    expect(screen.getAllByText(/COP/).length).toBeGreaterThan(0);
    expect(container).not.toHaveTextContent('¥');
  });

  it('直接消费统一设备指标，不根据总数重新计算离线数', () => {
    render(<DashboardPage />);

    expect(screen.getByText('在线 85 | 离线 14')).toBeInTheDocument();
    expect(screen.getByText('充电中 10 | 可用 73 | 故障 2')).toBeInTheDocument();
  });
});
