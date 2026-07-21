'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_BASE_URL, API_ENDPOINTS } from '@/lib/constants';
import { getAccessToken } from '@/lib/auth';
import { getTenantId } from '@/lib/tenant';
import { useAuthStore } from '@/store/authStore';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';
import { TrendChart } from '@/features/dashboard/TrendChart';
import { useI18n } from '@/lib/i18n';

const fetcher = <T,>(url: string) => apiGet<T>(url);

interface RevenueStat {
  date: string;
  total_revenue: number;
}

interface EnergyStat {
  date: string;
  total_energy_kwh: number;
}

interface OrdersStat {
  date: string;
  order_count: number;
}

export default function StatisticsPage() {
  const [days, setDays] = useState(30);
  const reportType = 'revenue';
  const { t } = useI18n();

  const { data: revenueData, isLoading: revenueLoading } = useSWR<RevenueStat[]>(
    `${API_ENDPOINTS.STATISTICS_REVENUE}?days=${days}&group_by=day`,
    fetcher
  );

  const { data: energyData, isLoading: energyLoading } = useSWR<EnergyStat[]>(
    `${API_ENDPOINTS.STATISTICS_ENERGY}?days=${days}&group_by=day`,
    fetcher
  );

  const { data: ordersData, isLoading: ordersLoading } = useSWR<OrdersStat[]>(
    `${API_ENDPOINTS.STATISTICS_ORDERS}?days=${days}&group_by=day`,
    fetcher
  );

  const handleExport = async () => {
    try {
      const tenantId = getTenantId(useAuthStore.getState().user);
      const response = await fetch(
        `${API_BASE_URL}${API_ENDPOINTS.STATISTICS_EXPORT}?report_type=${reportType}&days=${days}&format=csv`,
        {
          headers: {
            Authorization: `Bearer ${getAccessToken() || ''}`,
            ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
          },
        }
      );
      if (!response.ok) {
        throw new Error(`Export failed with HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${reportType}_${days}days.csv`;
      a.click();
    } catch (error) {
      console.error('Export failed:', error);
      alert(t('导出失败'));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('统计报表')}</h1>
          <p className="text-slate-400 mt-1">{t('查看运营数据和趋势分析')}</p>
        </div>
        <div className="flex gap-4">
          <Select value={days.toString()} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="w-[150px] bg-slate-800/50 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-700">
              <SelectItem value="7">{t('最近 7 天')}</SelectItem>
              <SelectItem value="30">{t('最近 30 天')}</SelectItem>
              <SelectItem value="90">{t('最近 90 天')}</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleExport} className="bg-gradient-to-r from-purple-600 to-blue-600">
            <Download className="h-4 w-4 mr-2" />
            {t('导出报表')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">{t('收入报表')}</CardTitle>
            <p className="text-sm text-slate-400">{t(`过去 ${days} 天收入趋势`)}</p>
          </CardHeader>
          <CardContent>
            {revenueLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('加载中...')}</div>
            ) : revenueData ? (
              <div className="h-64">
                <TrendChart
                  data={revenueData.map((item) => ({ date: item.date, value: item.total_revenue }))}
                  title={t('收入')}
                  color="hsl(var(--chart-primary))"
                  unit="¥"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('暂无数据')}</div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">{t('充电量报表')}</CardTitle>
            <p className="text-sm text-slate-400">{t(`过去 ${days} 天充电量趋势`)}</p>
          </CardHeader>
          <CardContent>
            {energyLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('加载中...')}</div>
            ) : energyData ? (
              <div className="h-64">
                <TrendChart
                  data={energyData.map((item) => ({ date: item.date, value: item.total_energy_kwh }))}
                  title={t('充电量')}
                  color="hsl(var(--chart-secondary))"
                  unit="kWh"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('暂无数据')}</div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-white">{t('订单报表')}</CardTitle>
            <p className="text-sm text-slate-400">{t(`过去 ${days} 天订单趋势`)}</p>
          </CardHeader>
          <CardContent>
            {ordersLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('加载中...')}</div>
            ) : ordersData ? (
              <div className="h-64">
                <TrendChart
                  data={ordersData.map((item) => ({ date: item.date, value: item.order_count }))}
                  title={t('订单数')}
                  color="hsl(var(--chart-accent))"
                  unit=""
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">{t('暂无数据')}</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
