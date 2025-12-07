/**
 * 充电桩详情和监控页面
 * 显示充电桩的详细信息以及过去10天的监控数据图表
 */

"use client";

import React, { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";

type ChargerDetail = {
  id: string;
  vendor: string | null;
  model: string | null;
  status: string;
  location: {
    latitude: number | null;
    longitude: number | null;
    address: string;
  };
  price_per_kwh: number;
  charging_rate: number;
};

type DailyStats = {
  date: string;
  charging_sessions: number;
  total_energy_kwh: number;
  total_duration_minutes: number;
  total_revenue: number;
  avg_energy_per_session: number;
  avg_duration_per_session: number;
};

type HistoryData = {
  charger_id: string;
  period: {
    start: string;
    end: string;
    days: number;
  };
  daily_stats: DailyStats[];
  total_stats: {
    total_sessions: number;
    total_energy_kwh: number;
    total_duration_minutes: number;
    total_revenue: number;
    avg_energy_per_session: number;
    avg_duration_per_session: number;
  };
  charger_info: ChargerDetail;
};

const fetcher = async (url: string) => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const COLORS = ["#007AFF", "#34c759", "#ff9500", "#ff3b30", "#5ac8fa", "#8b5cf6"];

export default function ChargerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const chargerId = params.id as string;
  const [days, setDays] = useState(10);

  // 获取充电桩详情
  const { data: chargerDetail, error: detailError } = useSWR<ChargerDetail>(
    chargerId ? `${apiBase}/api/v1/chargers/${chargerId}` : null,
    fetcher
  );

  // 获取历史数据
  const { data: historyData, error: historyError } = useSWR<HistoryData>(
    chargerId ? `${apiBase}/api/v1/statistics/charger/${chargerId}/history?days=${days}` : null,
    fetcher
  );

  if (detailError || historyError) {
    return (
      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        color: "#fff",
        padding: 20,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ fontSize: 24, marginBottom: 16 }}>加载失败</h2>
          <p style={{ color: "#aaa", marginBottom: 24 }}>
            {detailError?.message || historyError?.message}
          </p>
          <button
            onClick={() => router.push("/chargers")}
            style={{
              padding: "12px 24px",
              background: "#007AFF",
              border: "none",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            返回列表
          </button>
        </div>
      </div>
    );
  }

  if (!chargerDetail || !historyData) {
    return (
      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        color: "#fff",
        padding: 20,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        <div>加载中...</div>
      </div>
    );
  }

  const { daily_stats, total_stats, charger_info } = historyData;

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
      color: "#fff",
      padding: 20,
      fontFamily: "ui-sans-serif, system-ui",
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <h1 style={{ fontSize: 28, fontWeight: "700", marginBottom: 8, color: "#fff" }}>
              {chargerId} - 监控数据
            </h1>
            <div style={{ fontSize: 14, color: "#aaa" }}>
              {charger_info.vendor} {charger_info.model}
            </div>
          </div>
          <button
            onClick={() => router.push("/chargers")}
            style={{
              padding: "10px 20px",
              background: "rgba(255,255,255,0.1)",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            ← 返回列表
          </button>
        </div>

        {/* 时间范围选择 */}
        <div style={{ display: "flex", gap: 8 }}>
          {[7, 10, 15, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                padding: "6px 12px",
                background: days === d ? "#007AFF" : "rgba(255,255,255,0.05)",
                border: `1px solid ${days === d ? "#007AFF" : "rgba(255,255,255,0.2)"}`,
                borderRadius: 6,
                color: "#fff",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              过去{d}天
            </button>
          ))}
        </div>
      </div>

      {/* 总计统计卡片 */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: 16,
        marginBottom: 32,
      }}>
        <StatCard label="总充电次数" value={total_stats.total_sessions} unit="次" color="#007AFF" />
        <StatCard label="总充电量" value={total_stats.total_energy_kwh.toFixed(2)} unit="kWh" color="#34c759" />
        <StatCard label="总时长" value={Math.round(total_stats.total_duration_minutes)} unit="分钟" color="#5ac8fa" />
        <StatCard label="总收入" value={total_stats.total_revenue.toLocaleString()} unit="COP" color="#ff9500" />
        <StatCard label="平均电量" value={total_stats.avg_energy_per_session.toFixed(2)} unit="kWh/次" color="#8b5cf6" />
        <StatCard label="平均时长" value={Math.round(total_stats.avg_duration_per_session)} unit="分钟/次" color="#ff3b30" />
      </div>

      {/* 图表区域 */}
      <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
        {/* 充电次数趋势 */}
        <ChartCard title="每日充电次数">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={daily_stats}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey="date"
                stroke="#aaa"
                tick={{ fill: "#aaa", fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
              />
              <YAxis stroke="#aaa" tick={{ fill: "#aaa", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "rgba(0,0,0,0.8)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 8,
                  color: "#fff",
                }}
              />
              <Bar dataKey="charging_sessions" fill="#007AFF" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 充电量趋势 */}
        <ChartCard title="每日充电量 (kWh)">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={daily_stats}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey="date"
                stroke="#aaa"
                tick={{ fill: "#aaa", fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
              />
              <YAxis stroke="#aaa" tick={{ fill: "#aaa", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "rgba(0,0,0,0.8)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 8,
                  color: "#fff",
                }}
              />
              <Area
                type="monotone"
                dataKey="total_energy_kwh"
                stroke="#34c759"
                fill="#34c759"
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 收入趋势 */}
        <ChartCard title="每日收入 (COP)">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={daily_stats}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey="date"
                stroke="#aaa"
                tick={{ fill: "#aaa", fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
              />
              <YAxis stroke="#aaa" tick={{ fill: "#aaa", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "rgba(0,0,0,0.8)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 8,
                  color: "#fff",
                }}
                formatter={(value: number) => value.toLocaleString()}
              />
              <Line
                type="monotone"
                dataKey="total_revenue"
                stroke="#ff9500"
                strokeWidth={2}
                dot={{ fill: "#ff9500", r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 充电时长趋势 */}
        <ChartCard title="每日充电时长 (分钟)">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={daily_stats}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey="date"
                stroke="#aaa"
                tick={{ fill: "#aaa", fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
              />
              <YAxis stroke="#aaa" tick={{ fill: "#aaa", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "rgba(0,0,0,0.8)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 8,
                  color: "#fff",
                }}
              />
              <Area
                type="monotone"
                dataKey="total_duration_minutes"
                stroke="#5ac8fa"
                fill="#5ac8fa"
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

function StatCard({ label, value, unit, color }: { label: string; value: string | number; unit: string; color: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 20,
      border: `1px solid ${color}40`,
    }}>
      <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: "700", color, marginBottom: 4 }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: "#888" }}>{unit}</div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 24,
      border: "1px solid rgba(255,255,255,0.1)",
    }}>
      <h3 style={{ fontSize: 18, fontWeight: "600", marginBottom: 20, color: "#fff" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

