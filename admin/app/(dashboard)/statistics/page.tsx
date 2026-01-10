'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Download, BarChart3 } from 'lucide-react';
import { TrendChart } from '@/features/dashboard/TrendChart';

const fetcher = (url: string) => apiGet(url);

export default function StatisticsPage() {
  const [days, setDays] = useState(30);
  const [reportType, setReportType] = useState<'revenue' | 'energy' | 'orders'>('revenue');

  const { data: revenueData, isLoading: revenueLoading } = useSWR(
    `${API_ENDPOINTS.STATISTICS_REVENUE}?days=${days}&group_by=day`,
    fetcher
  );

  const { data: energyData, isLoading: energyLoading } = useSWR(
    `${API_ENDPOINTS.STATISTICS_ENERGY}?days=${days}&group_by=day`,
    fetcher
  );

  const { data: ordersData, isLoading: ordersLoading } = useSWR(
    `${API_ENDPOINTS.STATISTICS_ORDERS}?days=${days}&group_by=day`,
    fetcher
  );

  const handleExport = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}${API_ENDPOINTS.STATISTICS_EXPORT}?report_type=${reportType}&days=${days}&format=csv`
      );
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${reportType}_${days}days.csv`;
      a.click();
    } catch (error) {
      console.error('Export failed:', error);
      alert('导出失败');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">统计报表</h1>
          <p className="text-slate-400 mt-1">查看运营数据和趋势分析</p>
        </div>
        <div className="flex gap-4">
          <Select value={days.toString()} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="w-[150px] bg-slate-800/50 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-700">
              <SelectItem value="7">最近 7 天</SelectItem>
              <SelectItem value="30">最近 30 天</SelectItem>
              <SelectItem value="90">最近 90 天</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleExport} className="bg-gradient-to-r from-purple-600 to-blue-600">
            <Download className="h-4 w-4 mr-2" />
            导出报表
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">收入报表</CardTitle>
            <p className="text-sm text-slate-400">过去 {days} 天收入趋势</p>
          </CardHeader>
          <CardContent>
            {revenueLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">加载中...</div>
            ) : revenueData ? (
              <div className="h-64">
                <TrendChart
                  data={revenueData.map((item: any) => ({ date: item.date, value: item.total_revenue }))}
                  title="收入"
                  color="hsl(var(--chart-primary))"
                  unit="¥"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">暂无数据</div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">充电量报表</CardTitle>
            <p className="text-sm text-slate-400">过去 {days} 天充电量趋势</p>
          </CardHeader>
          <CardContent>
            {energyLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">加载中...</div>
            ) : energyData ? (
              <div className="h-64">
                <TrendChart
                  data={energyData.map((item: any) => ({ date: item.date, value: item.total_energy_kwh }))}
                  title="充电量"
                  color="hsl(var(--chart-secondary))"
                  unit="kWh"
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">暂无数据</div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700 lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-white">订单报表</CardTitle>
            <p className="text-sm text-slate-400">过去 {days} 天订单趋势</p>
          </CardHeader>
          <CardContent>
            {ordersLoading ? (
              <div className="h-64 flex items-center justify-center text-slate-400">加载中...</div>
            ) : ordersData ? (
              <div className="h-64">
                <TrendChart
                  data={ordersData.map((item: any) => ({ date: item.date, value: item.order_count }))}
                  title="订单数"
                  color="hsl(var(--chart-accent))"
                  unit=""
                />
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-slate-400">暂无数据</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}