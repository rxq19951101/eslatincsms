'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS, REFRESH_INTERVAL } from '@/lib/constants';
import { DashboardSiteItem, DashboardSummary, DashboardTrends, SiteListItem } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Zap,
  DollarSign,
  Users,
  AlertTriangle,
  Activity,
  Battery,
} from 'lucide-react';
import { TrendChart } from '@/features/dashboard/TrendChart';
import { useI18n } from '@/lib/i18n';

const fetcher = (url: string) => apiGet(url);

const asNumber = (value: number | string | null | undefined, fallback = 0): number => {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export default function DashboardPage() {
  const { t } = useI18n();
  const days = 7;
  const [selectedSiteId, setSelectedSiteId] = useState<string>('all');

  // 站点列表（用于下拉选择）
  const { data: sites } = useSWR<SiteListItem[]>(API_ENDPOINTS.SITES, fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    revalidateOnFocus: true,
  });

  // 获取 Dashboard 概览数据
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useSWR<DashboardSummary>(
    API_ENDPOINTS.DASHBOARD_SUMMARY,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL, // 30 秒自动刷新
      revalidateOnFocus: true,
    }
  );

  // 站点维度汇总（用于“站点运营概览”与站点视角 KPI）
  const { data: siteStats, error: siteStatsError, isLoading: siteStatsLoading } = useSWR<DashboardSiteItem[]>(
    `${API_ENDPOINTS.DASHBOARD_SITES}?days=${days}&limit=200`,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL,
      revalidateOnFocus: true,
    }
  );

  // 获取趋势数据
  const trendsUrl =
    selectedSiteId === 'all'
      ? `${API_ENDPOINTS.DASHBOARD_TRENDS}?days=${days}`
      : `${API_ENDPOINTS.DASHBOARD_TRENDS}?days=${days}&site_id=${encodeURIComponent(selectedSiteId)}`;

  const { data: trends, error: trendsError, isLoading: trendsLoading } = useSWR<DashboardTrends>(
    trendsUrl,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL,
      revalidateOnFocus: true,
    }
  );

  const selectedSite = useMemo(() => {
    if (selectedSiteId === 'all') return null;
    return (sites || []).find((s) => s.id === selectedSiteId) || null;
  }, [selectedSiteId, sites]);

  const selectedSiteStat = useMemo(() => {
    if (selectedSiteId === 'all') return null;
    return (siteStats || []).find((s) => s.site_id === selectedSiteId) || null;
  }, [selectedSiteId, siteStats]);

  const sortedSiteStats = useMemo(() => {
    const list = siteStats || [];
    return [...list].sort((a, b) => {
      if ((b.revenue || 0) !== (a.revenue || 0)) return (b.revenue || 0) - (a.revenue || 0);
      if ((b.energy_kwh || 0) !== (a.energy_kwh || 0)) return (b.energy_kwh || 0) - (a.energy_kwh || 0);
      return (b.orders_count || 0) - (a.orders_count || 0);
    });
  }, [siteStats]);

  const normalizedTrends = useMemo<DashboardTrends | undefined>(() => {
    if (!trends) return undefined;
    const normalize = (items: DashboardTrends['energy_trend']) =>
      items.map((item) => ({ ...item, value: asNumber(item.value) }));
    return {
      energy_trend: normalize(trends.energy_trend || []),
      revenue_trend: normalize(trends.revenue_trend || []),
      orders_trend: normalize(trends.orders_trend || []),
    };
  }, [trends]);

  // KPI 卡片数据
  const kpiCards = useMemo(() => {
    const common = [
      {
        title: t('用户统计'),
        value: summary?.total_users || 0,
        subtitle: t(`总用户 ${summary?.total_users || 0} | 今日活跃 ${summary?.active_users_today || 0}`),
        icon: Users,
        color: 'from-pink-600 to-pink-800',
        iconBg: 'bg-pink-600/20',
      },
      {
        title: t('告警统计'),
        value: summary?.critical_alerts || 0,
        subtitle: t(`严重 ${summary?.critical_alerts || 0} | 警告 ${summary?.warning_alerts || 0} | 信息 ${summary?.info_alerts || 0}`),
        icon: AlertTriangle,
        color: 'from-red-600 to-red-800',
        iconBg: 'bg-red-600/20',
      },
    ];

    if (selectedSiteId === 'all') {
      return [
        {
          title: t('充电桩总数'),
          value: summary?.total_charge_points || 0,
          subtitle: t(`在线 ${summary?.online_charge_points || 0} | 离线 ${summary?.offline_charge_points || 0}`),
          icon: Zap,
          color: 'from-purple-600 to-purple-800',
          iconBg: 'bg-purple-600/20',
        },
        {
          title: t('充电桩状态'),
          value: summary?.charging_charge_points || 0,
          subtitle: t(`充电中 ${summary?.charging_charge_points || 0} | 可用 ${summary?.available_charge_points || 0} | 故障 ${summary?.faulted_charge_points || 0}`),
          icon: Activity,
          color: 'from-blue-600 to-blue-800',
          iconBg: 'bg-blue-600/20',
        },
        {
          title: t('今日数据'),
          value: summary?.today_orders || 0,
          subtitle: `${t('订单')} ${summary?.today_orders || 0} | ${t('充电量')} ${asNumber(summary?.today_energy_kwh).toFixed(2)} kWh`,
          icon: Battery,
          color: 'from-green-600 to-green-800',
          iconBg: 'bg-green-600/20',
        },
        {
          title: t('今日收入'),
          value: `¥${asNumber(summary?.today_revenue).toFixed(2)}`,
          subtitle: `${t('订单')} ${summary?.today_orders || 0}`,
          icon: DollarSign,
          color: 'from-yellow-600 to-yellow-800',
          iconBg: 'bg-yellow-600/20',
        },
        ...common,
      ];
    }

    const ss = selectedSiteStat;
    const cpTotal = ss?.charge_points_count || 0;
    const cpOnline = ss?.online_charge_points_count || 0;
    const cpFaulted = ss?.faulted_charge_points || 0;
    const cpCharging = ss?.charging_charge_points || 0;
    const cpAvailable = ss?.available_charge_points || 0;
    const orders = ss?.orders_count || 0;
    const energy = asNumber(ss?.energy_kwh);
    const revenue = asNumber(ss?.revenue);

    return [
      {
        title: `${t('站点')} ${t('充电桩总数')}`,
        value: cpTotal,
        subtitle: `${t('在线')} ${cpOnline} | ${t('总数')} ${cpTotal}`,
        icon: Zap,
        color: 'from-purple-600 to-purple-800',
        iconBg: 'bg-purple-600/20',
      },
      {
        title: `${t('站点')} ${t('健康')}`,
        value: cpFaulted,
        subtitle: `${t('故障')} ${cpFaulted} | ${t('充电中')} ${cpCharging} | ${t('可用')} ${cpAvailable}`,
        icon: Activity,
        color: 'from-blue-600 to-blue-800',
        iconBg: 'bg-blue-600/20',
      },
      {
        title: t(`近${days}天订单`),
        value: orders,
        subtitle: `${t('充电量')} ${energy.toFixed(2)} kWh`,
        icon: Battery,
        color: 'from-green-600 to-green-800',
        iconBg: 'bg-green-600/20',
      },
      {
        title: t(`近${days}天收入`),
        value: `¥${revenue.toFixed(2)}`,
        subtitle: `${t('订单')} ${orders}`,
        icon: DollarSign,
        color: 'from-yellow-600 to-yellow-800',
        iconBg: 'bg-yellow-600/20',
      },
      ...common,
    ];
  }, [days, selectedSiteId, selectedSiteStat, summary, t]);

  if (summaryLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">{t('加载中...')}</div>
      </div>
    );
  }

  if (summaryError) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{t('加载失败，请刷新页面重试')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('dashboard')}</h1>
          <p className="text-slate-400 mt-1">
            {selectedSiteId === 'all'
              ? t('租户汇总 + 站点维度运营分析')
              : t(`站点视角：${selectedSite?.name || selectedSiteId}`)}
          </p>
        </div>

        <div className="w-[280px]">
          <Select value={selectedSiteId} onValueChange={setSelectedSiteId}>
            <SelectTrigger className="bg-slate-800/50 border-slate-700">
              <SelectValue placeholder={t('选择站点')} />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-700">
              <SelectItem value="all">{t('全部站点（租户汇总）')}</SelectItem>
              {(sites || []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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

      {/* Site Analytics Table */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
        <CardHeader>
          <CardTitle className="text-white">{t(`站点运营概览（近 ${days} 天）`)}</CardTitle>
          <p className="text-sm text-slate-400">{t('按站点拆分：在线/故障、订单、充电量、收入（点击行可切换站点视角）')}</p>
        </CardHeader>
        <CardContent>
          {siteStatsLoading ? (
            <div className="text-slate-400">{t('加载中...')}</div>
          ) : siteStatsError ? (
            <div className="text-red-400">{t('加载失败')}</div>
          ) : sortedSiteStats.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('站点')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('在线/总桩')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('故障')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('订单')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('充电量')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('收入')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSiteStats.slice(0, 50).map((s) => {
                    const isSelected = selectedSiteId !== 'all' && s.site_id === selectedSiteId;
                    return (
                      <tr
                        key={s.site_id}
                        className={[
                          'border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer',
                          isSelected ? 'bg-slate-700/30' : '',
                        ].join(' ')}
                        onClick={() => setSelectedSiteId(s.site_id)}
                      >
                        <td className="py-3 px-4">
                          <div className="text-white font-medium">{s.site_name}</div>
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {s.online_charge_points_count}/{s.charge_points_count}
                        </td>
                        <td className="py-3 px-4 text-slate-300">{s.faulted_charge_points}</td>
                        <td className="py-3 px-4 text-slate-300">{s.orders_count}</td>
                        <td className="py-3 px-4 text-slate-300">{asNumber(s.energy_kwh).toFixed(2)} kWh</td>
                        <td className="py-3 px-4 text-slate-300">¥{asNumber(s.revenue).toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-slate-400">{t('暂无数据')}</div>
          )}
        </CardContent>
      </Card>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Energy Trend Chart */}
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
          <CardHeader>
            <CardTitle className="text-white">{t('充电量趋势')}</CardTitle>
            <p className="text-sm text-slate-400">
              {t(`过去 ${days} 天充电量（kWh）${selectedSiteId === 'all' ? '（租户汇总）' : `（${selectedSite?.name || selectedSiteId}）`}`)}
            </p>
          </CardHeader>
          <CardContent>
            {trendsLoading ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-slate-400">{t('加载中...')}</div>
              </div>
            ) : trendsError ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-red-400">{t('加载失败')}</div>
              </div>
            ) : normalizedTrends?.energy_trend ? (
              <div className="h-64">
                <TrendChart
                  data={normalizedTrends.energy_trend}
                  title={t('充电量')}
                  color="hsl(var(--chart-primary))"
                  unit="kWh"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                <p>{t('暂无数据')}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Revenue Trend Chart */}
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
          <CardHeader>
            <CardTitle className="text-white">{t('收入趋势')}</CardTitle>
            <p className="text-sm text-slate-400">
              {t(`过去 ${days} 天收入（¥）${selectedSiteId === 'all' ? '（租户汇总）' : `（${selectedSite?.name || selectedSiteId}）`}`)}
            </p>
          </CardHeader>
          <CardContent>
            {trendsLoading ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-slate-400">{t('加载中...')}</div>
              </div>
            ) : trendsError ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-red-400">{t('加载失败')}</div>
              </div>
          ) : normalizedTrends?.revenue_trend ? (
              <div className="h-64">
                <TrendChart
                  data={normalizedTrends.revenue_trend}
                  title={t('收入')}
                  color="hsl(var(--chart-secondary))"
                  unit="¥"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">
                <p>{t('暂无数据')}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Orders Trend Chart */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 shadow-lg">
        <CardHeader>
          <CardTitle className="text-white">{t('订单趋势')}</CardTitle>
          <p className="text-sm text-slate-400">
              {t(`过去 ${days} 天订单数量${selectedSiteId === 'all' ? '（租户汇总）' : `（${selectedSite?.name || selectedSiteId}）`}`)}
          </p>
        </CardHeader>
        <CardContent>
          {trendsLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-slate-400">{t('加载中...')}</div>
            </div>
          ) : trendsError ? (
            <div className="flex items-center justify-center h-64">
                <div className="text-red-400">{t('加载失败')}</div>
            </div>
          ) : normalizedTrends?.orders_trend ? (
            <div className="h-64">
              <TrendChart
                  data={normalizedTrends.orders_trend}
                title={t('订单数')}
                color="hsl(var(--chart-accent))"
                unit=""
              />
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-400">
              <p>{t('暂无数据')}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
