import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DashboardPage from '../page';

// Mock SWR
vi.mock('swr', () => ({
  default: (key: string, fetcher: Function) => {
    // 模拟数据加载
    const mockData = {
      '/api/v1/dashboard/summary': {
        total_charge_points: 100,
        online_charge_points: 85,
        offline_charge_points: 15,
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
});