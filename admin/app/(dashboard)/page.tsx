'use client';

import { useEffect } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS, REFRESH_INTERVAL } from '@/lib/constants';
import { DashboardSummary, DashboardTrends } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Zap,
  Plug,
  DollarSign,
  FileText,
  Users,
  AlertTriangle,
  TrendingUp,
  Activity,
  Battery,
} from 'lucide-react';
import { TrendChart } from '@/features/dashboard/TrendChart';

const fetcher = (url: string) => apiGet(url);

export default function DashboardPage() {
  // 获取 Dashboard 概览数据
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useSWR<DashboardSummary>(
    API_ENDPOINTS.DASHBOARD_SUMMARY,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL, // 30 秒自动刷新
      revalidateOnFocus: true,
    }
  );

  // 获取趋势数据
  const { data: trends, error: trendsError, isLoading: trendsLoading } = useSWR<DashboardTrends>(
    `${API_ENDPOINTS.DASHBOARD_TRENDS}?days=7`,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL,
      revalidateOnFocus: true,
    }
  );

  // KPI 卡片数据
  const kpiCards = [
    {
      title: '充电桩总数',
      value: summary?.total_charge_points || 0,
      subtitle: `在线 ${summary?.online_charge_points || 0} | 离线 ${summary?.offline_charge_points || 0}`,
      icon: Zap,
      color: 'from-purple-600 to-purple-800',
      iconBg: 'bg-purple-600/20',
    },
    {
      title: '充电桩状态',
      value: summary?.charging_charge_points || 0,
      subtitle: `充电中 ${summary?.charging_charge_points || 0} | 可用 ${summary?.available_charge_points || 0}`,
      icon: Activity,
      color: 'from-blue-600 to-blue-800',
      iconBg: 'bg-blue-600/20',
    },
    {
      title: '今日数据',
      value: summary?.today_orders || 0,
      subtitle: `订单 ${summary?.today_orders || 0} | 充电量 ${summary?.today_energy_kwh?.toFixed(2) || 0} kWh`,
      icon: Battery,
      color: 'from-green-600 to-green-800',
      iconBg: 'bg-green-600/20',
    },
    {
      title: '今日收入',
      value: `¥${summary?.today_revenue?.toFixed(2) || 0}`,
      subtitle: `订单 ${summary?.today_orders || 0} 笔`,
      icon: DollarSign,
      color: 'from-yellow-600 to-yellow-800',
      iconBg: 'bg-yellow-600/20',
    },
    {
      title: '用户统计',
      value: summary?.total_users || 0,
      subtitle: `总用户 ${summary?.total_users || 0} | 今日活跃 ${summary?.active_users_today || 0}`,
      icon: Users,
      color: 'from-pink-600 to-pink-800',
      iconBg: 'bg-pink-600/20',
    },
    {
      title: '告警统计',
      value: summary?.critical_alerts || 0,
      subtitle: `严重 ${summary?.critical_alerts || 0} | 警告 ${summary?.warning_alerts || 0} | 信息 ${summary?.info_alerts || 0}`,
      icon: AlertTriangle,
      color: 'from-red-600 to-red-800',
      iconBg: 'bg-red-600/20',
    },
  ];

  if (summaryLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">加载中...</div>
      </div>
    );
  }

  if (summaryError) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">加载失败，请刷新页面重试</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">仪表板</h1>
        <p className="text-slate-400 mt-1">充电桩运营平台概览</p>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {kpiCards.map((card, index) => {
          const Icon = card.icon;
          return (
            <Card
              key={index}
              className="bg-slate-800/80 backdrop-blur-sm border-slate-700 hover:border-purple-500/50 transition-colors shadow-lg"
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-slate-300">{card.title}</CardTitle>
                <div className={`p-2 rounded-lg ${card.iconBg}`}>
                  <Icon className={`h-5 w-5 bg-gradient-to-br ${card.color} bg-clip-text text-transparent`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-white mb-1">{card.value}</div>
                <p className="text-xs text-slate-400">{card.subtitle}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Energy Trend Chart */}
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
          <CardHeader>
            <CardTitle className="text-white">充电量趋势</CardTitle>
            <p className="text-sm text-slate-400">过去 7 天充电量（kWh）</p>
          </CardHeader>
          <CardContent>
            {trendsLoading ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-slate-400">加载中...</div>
              </div>
            ) : trendsError ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-red-400">加载失败</div>
              </div>
            ) : trends?.energy_trend ? (
              <div className="h-64">
                <TrendChart
                  data={trends.energy_trend}
                  title="充电量"
                  color="hsl(var(--chart-primary))"
                  unit="kWh"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                <p>暂无数据</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Revenue Trend Chart */}
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
          <CardHeader>
            <CardTitle className="text-white">收入趋势</CardTitle>
            <p className="text-sm text-slate-400">过去 7 天收入（¥）</p>
          </CardHeader>
          <CardContent>
            {trendsLoading ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-slate-400">加载中...</div>
              </div>
            ) : trendsError ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-red-400">加载失败</div>
              </div>
            ) : trends?.revenue_trend ? (
              <div className="h-64">
                <TrendChart
                  data={trends.revenue_trend}
                  title="收入"
                  color="hsl(var(--chart-secondary))"
                  unit="¥"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                <p>暂无数据</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Orders Trend Chart */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
        <CardHeader>
          <CardTitle className="text-white">订单趋势</CardTitle>
          <p className="text-sm text-slate-400">过去 7 天订单数量</p>
        </CardHeader>
        <CardContent>
          {trendsLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-slate-400">加载中...</div>
            </div>
          ) : trendsError ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-red-400">加载失败</div>
            </div>
          ) : trends?.orders_trend ? (
            <div className="h-64">
              <TrendChart
                data={trends.orders_trend}
                title="订单数"
                color="hsl(var(--chart-accent))"
                unit=""
              />
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-400">
              <p>暂无数据</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}