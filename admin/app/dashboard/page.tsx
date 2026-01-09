/**
 * 仪表板页面 (Dashboard)
 * 显示运营数据总览、实时监控和趋势图表
 * 使用 shadcn/ui 和 Tailwind CSS
 * 
 * 优化：首屏只加载 summary，其他数据延迟加载
 */

"use client";

import React, { useState, lazy, Suspense } from "react";
import useSWR from "swr";
import { authenticatedFetch } from "../utils/api";
import { getApiBase } from "../utils/api";
import { Card, CardContent } from "@/components/ui/card";
import { KPICard } from "@/components/dashboard/KPICard";
import { Zap, Plug, DollarSign, AlertTriangle } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { format } from "date-fns";

const DashboardCharts = lazy(() => import("../components/dashboard/DashboardCharts"));
const DashboardTables = lazy(() => import("../components/dashboard/DashboardTables"));

const fetcher = async <T = any>(url: string): Promise<T> => {
  const res = await authenticatedFetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
};

interface DashboardSummary {
  total_chargers: number;
  online_chargers: number;
  offline_chargers: number;
  charging_chargers: number;
  today_energy_kwh: number;
  today_revenue_cop: number;
  active_users: number;
  today_orders: number;
  online_rate: number;
  fault_rate: number;
}

interface Alert {
  id: string;
  type: string;
  severity: "critical" | "warning" | "info";
  message: string;
  charge_point_id?: string;
  created_at: string;
  status: "pending" | "acknowledged" | "resolved";
}

// Skeleton 加载组件
function ChartsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 mb-6 lg:grid-cols-2">
      <Card>
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/4"></div>
            <div className="h-64 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/4"></div>
            <div className="h-64 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TablesSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/3"></div>
            <div className="h-32 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-muted rounded w-1/3"></div>
            <div className="h-32 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const apiBase = getApiBase();
  const [selectedMonth, setSelectedMonth] = useState(format(new Date(), "MMM yyyy"));

  // 首屏只加载 summary 和 alerts（用于 KPI 卡片）
  const { data: summary, error: summaryError, isLoading: summaryLoading } = useSWR<DashboardSummary>(
    `${apiBase}/api/v1/dashboard/summary`,
    fetcher,
    { refreshInterval: 30000 } // 30秒刷新
  );

  const { data: alerts, error: alertsError } = useSWR<Alert[]>(
    `${apiBase}/api/v1/alerts?status=pending&limit=100`,
    fetcher,
    { refreshInterval: 30000 } // 30秒刷新（从10秒改为30秒）
  );

  const activeAlertsCount = alerts?.filter((a) => a.status === "pending")?.length || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground mt-1">实时运营数据总览</p>
        </div>
        <Select value={selectedMonth} onValueChange={setSelectedMonth}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Select month" />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 12 }, (_, i) => {
              const date = new Date();
              date.setMonth(date.getMonth() - i);
              const monthStr = format(date, "MMM yyyy");
              return (
                <SelectItem key={monthStr} value={monthStr}>
                  {monthStr}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>

      {/* KPI Cards - 首屏立即显示 */}
      <div className="grid grid-cols-1 gap-4 mb-6 md:grid-cols-2 lg:grid-cols-4">
        {summaryLoading ? (
          <>
            <Card><CardContent className="p-6"><div className="animate-pulse">加载中...</div></CardContent></Card>
            <Card><CardContent className="p-6"><div className="animate-pulse">加载中...</div></CardContent></Card>
            <Card><CardContent className="p-6"><div className="animate-pulse">加载中...</div></CardContent></Card>
            <Card><CardContent className="p-6"><div className="animate-pulse">加载中...</div></CardContent></Card>
          </>
        ) : (
          <>
            <KPICard
              title="活跃充电桩"
              value={summary?.online_chargers || 0}
              icon={Plug}
              iconBgColor="bg-purple-500"
            />
            <KPICard
              title="充电中"
              value={summary?.charging_chargers || 0}
              icon={Zap}
              iconBgColor="bg-green-500"
            />
            <KPICard
              title="今日收入"
              value={summary?.today_revenue_cop ? `${summary.today_revenue_cop.toLocaleString()} COP` : "0 COP"}
              icon={DollarSign}
              iconBgColor="bg-pink-500"
            />
            <KPICard
              title="活跃告警"
              value={activeAlertsCount}
              icon={AlertTriangle}
              iconBgColor="bg-blue-500"
            />
          </>
        )}
      </div>

      {/* Charts Row - 延迟加载 */}
      <Suspense fallback={<ChartsSkeleton />}>
        <DashboardCharts />
      </Suspense>

      {/* Tables Row - 延迟加载 */}
      <Suspense fallback={<TablesSkeleton />}>
        <DashboardTables />
      </Suspense>
    </div>
  );
}
