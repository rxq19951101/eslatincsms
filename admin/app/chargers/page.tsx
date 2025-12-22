/**
 * 本文件为 /chargers 页面：充电桩监测大屏视图。
 * 使用 SWR 每 3s 拉取状态，暗色主题、圆环仪表、统计卡片。
 * 仅用于本地测试与演示。
 */

"use client";

import React, { useState, useEffect, useMemo } from "react";
import useSWR from "swr";
import { QRCodeSVG } from "qrcode.react";
import { getApiBase, getApiBaseWithValidation } from "../utils/api";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";

type Charger = {
  id: string;
  status: string;
  last_seen: string;
  vendor?: string;
  model?: string;
  address?: string;
  location?: {
    latitude: number | null;
    longitude: number | null;
    address: string;
  };
  session?: {
    authorized: boolean;
    transaction_id: number | null;
    meter: number;
  };
  connector_type?: string;  // 充电头类型: GBT, Type1, Type2, CCS1, CCS2
  charging_rate?: number;  // 充电速率 (kW)
  price_per_kwh?: number;  // 每度电价格 (COP/kWh)
  is_configured?: boolean;  // 是否已配置
  has_location?: boolean;   // 是否有位置
  has_pricing?: boolean;    // 是否有价格
};

type HeartbeatData = {
  charger_id: string;
  period: {
    start: string;
    end: string;
    hours: number;
  };
  heartbeats: Array<{
    timestamp: string;
    health_status: string;
    interval_seconds: number | null;
  }>;
  health_stats: {
    normal: number;
    warning: number;
    abnormal: number;
  };
  avg_interval_seconds: number | null;
  total_heartbeats: number;
};

type StatusData = {
  charger_id: string;
  period: {
    start: string;
    end: string;
    hours: number;
  };
  timeline: Array<{
    timestamp: string;
    status: string;
    previous_status: string | null;
    duration_seconds: number | null;
  }>;
  hourly_status: Array<{
    hour: string;
    status_distribution: {
      Offline: number;
      Available: number;
      Charging: number;
      Faulted: number;
      Unavailable: number;
    };
  }>;
  total_status_distribution: {
    Offline: number;
    Available: number;
    Charging: number;
    Faulted: number;
    Unavailable: number;
  };
  current_status: string;
};

const fetcher = async <T = any>(url: string): Promise<T> => {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText || res.statusText}`);
    }
    return res.json();
  } catch (error: any) {
    // 提供更详细的错误信息
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      throw new Error(`无法连接到服务器: ${url}。请检查服务器是否运行，网络是否正常。`);
    }
    throw error;
  }
};

export default function ChargersPage() {
  // 验证API地址配置
  const { url: apiBase, error: configError } = getApiBaseWithValidation();
  const [filterType, setFilterType] = useState<"all" | "configured" | "unconfigured">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedChargerForCharts, setSelectedChargerForCharts] = useState<string | null>(null);
  
  // 构建API URL，根据筛选类型添加参数
  const apiUrl = filterType === "all" 
    ? `${apiBase}/api/v1/chargers`
    : `${apiBase}/api/v1/chargers?filter_type=${filterType}`;
  
  const { data: chargers = [], error: fetchError, isLoading, mutate } = useSWR<Charger[]>(
    // 如果配置错误，不发送请求
    configError ? null : apiUrl,
    fetcher,
    { refreshInterval: 3000 }
  );
  
  // 合并配置错误和请求错误
  const error = configError || fetchError;
  
  // 搜索过滤
  const filteredChargers = useMemo(() => {
    if (!searchQuery.trim()) {
      return chargers;
    }
    const query = searchQuery.toLowerCase();
    return chargers.filter((c: Charger) => 
      c.id.toLowerCase().includes(query) ||
      (c.vendor && c.vendor.toLowerCase().includes(query)) ||
      (c.model && c.model.toLowerCase().includes(query)) ||
      (c.address && c.address.toLowerCase().includes(query)) ||
      (c.location?.address && c.location.address.toLowerCase().includes(query))
    );
  }, [chargers, searchQuery]);
  
  // 获取选中充电桩的心跳和状态数据
  const { data: heartbeatData } = useSWR<HeartbeatData>(
    selectedChargerForCharts ? `${apiBase}/api/v1/statistics/charger/${selectedChargerForCharts}/heartbeat-history?hours=24` : null,
    fetcher,
    { refreshInterval: 10000 }
  );
  
  const { data: statusData } = useSWR<StatusData>(
    selectedChargerForCharts ? `${apiBase}/api/v1/statistics/charger/${selectedChargerForCharts}/status-timeline?hours=24` : null,
    fetcher,
    { refreshInterval: 10000 }
  );

  const isOffline = (lastSeen: string) => {
    const last = new Date(lastSeen).getTime();
    const now = Date.now();
    return now - last > 30000;
  };

  const stats = {
    total: filteredChargers.length,
    configured: filteredChargers.filter((c: Charger) => c.is_configured).length,
    unconfigured: filteredChargers.filter((c: Charger) => !c.is_configured).length,
    online: filteredChargers.filter((c: Charger) => !isOffline(c.last_seen)).length,
    available: filteredChargers.filter((c: Charger) => !isOffline(c.last_seen) && c.status === "Available").length,
    charging: filteredChargers.filter((c: Charger) => !isOffline(c.last_seen) && c.status === "Charging").length,
    offline: filteredChargers.filter((c: Charger) => isOffline(c.last_seen)).length,
  };

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
        <h1 style={{ fontSize: 28, fontWeight: "700", marginBottom: 8, color: "#fff" }}>
          充电桩监测中心
        </h1>
        <div style={{ display: "flex", gap: 16, fontSize: 14, color: "#aaa", marginBottom: 16 }}>
          <span>OCPP 1.6J Test Platform</span>
          <span>•</span>
          <span>实时刷新: 3秒</span>
        </div>
        
        {/* 搜索框和筛选标签 */}
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
          {/* 搜索框 */}
          <div style={{ flex: 1, minWidth: 300, maxWidth: 500 }}>
            <input
              type="text"
              placeholder="搜索充电桩 (ID、厂商、型号、地址)..."
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 16px",
                background: "rgba(255,255,255,0.1)",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 8,
                color: "#fff",
                fontSize: 14,
                outline: "none",
              }}
            />
          </div>
          
          {/* 筛选标签 */}
          <div style={{ display: "flex", gap: 12 }}>
            <FilterTab
              label="全部"
              count={chargers.length}
              active={filterType === "all"}
              onClick={() => setFilterType("all")}
            />
            <FilterTab
              label="已配置"
              count={chargers.filter((c) => c.is_configured).length}
              active={filterType === "configured"}
              onClick={() => setFilterType("configured")}
              color="#34c759"
            />
            <FilterTab
              label="未配置"
              count={chargers.filter((c) => !c.is_configured).length}
              active={filterType === "unconfigured"}
              onClick={() => setFilterType("unconfigured")}
              color="#ff9500"
            />
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 16,
        marginBottom: 32,
      }}>
        <StatCard label="总计" value={stats.total} color="#8b5cf6" />
        <StatCard label="已配置" value={stats.configured} color="#34c759" />
        <StatCard label="未配置" value={stats.unconfigured} color="#ff9500" />
        <StatCard label="在线" value={stats.online} color="#5ac8fa" />
        <StatCard label="可用" value={stats.available} color="#5ac8fa" />
        <StatCard label="充电中" value={stats.charging} color="#ff9500" />
        <StatCard label="离线" value={stats.offline} color="#ff3b30" />
      </div>
      
      {/* 图表区域 */}
      {selectedChargerForCharts && (
        <div style={{
          background: "rgba(255,255,255,0.05)",
          borderRadius: 12,
          padding: 24,
          marginBottom: 32,
          border: "1px solid rgba(255,255,255,0.1)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <h2 style={{ fontSize: 20, fontWeight: "600", color: "#fff" }}>
              监控图表: {selectedChargerForCharts}
            </h2>
            <button
              onClick={() => setSelectedChargerForCharts(null)}
              style={{
                padding: "8px 16px",
                background: "rgba(255,255,255,0.1)",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 6,
                color: "#fff",
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              关闭图表
            </button>
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(500px, 1fr))", gap: 24 }}>
            {/* 心跳折线图 */}
            {heartbeatData && (
              <ChartCard title="心跳健康状态 (过去24小时)">
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={heartbeatData.heartbeats?.slice(-50) || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="timestamp" 
                      stroke="#aaa"
                      tickFormatter={(value: string) => {
                        const date = new Date(value);
                        return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
                      }}
                    />
                    <YAxis stroke="#aaa" />
                    <Tooltip 
                      contentStyle={{
                        background: "#333",
                        border: "1px solid #555",
                        borderRadius: 5,
                        color: "#fff",
                      }}
                      labelFormatter={(value: string) => {
                        const date = new Date(value);
                        return date.toLocaleString();
                      }}
                    />
                    <Legend wrapperStyle={{ color: "#aaa" }} />
                    <Line 
                      type="monotone" 
                      dataKey="interval_seconds" 
                      name="心跳间隔(秒)" 
                      stroke="#5ac8fa" 
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
                <div style={{ marginTop: 16, display: "flex", gap: 16, fontSize: 12, color: "#aaa" }}>
                  <div>
                    <span style={{ color: "#34c759" }}>●</span> 正常: {heartbeatData.health_stats?.normal || 0}
                  </div>
                  <div>
                    <span style={{ color: "#ff9500" }}>●</span> 警告: {heartbeatData.health_stats?.warning || 0}
                  </div>
                  <div>
                    <span style={{ color: "#ff3b30" }}>●</span> 异常: {heartbeatData.health_stats?.abnormal || 0}
                  </div>
                </div>
              </ChartCard>
            )}
            
            {/* 状态分布图表 */}
            {statusData && (
              <ChartCard title="充电状态分布 (过去24小时)">
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={[
                        { name: "离线", value: statusData.total_status_distribution?.Offline || 0 },
                        { name: "空闲", value: statusData.total_status_distribution?.Available || 0 },
                        { name: "充电中", value: statusData.total_status_distribution?.Charging || 0 },
                      ]}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }: { name?: string; percent?: number }) => `${name || '未知'} ${((percent ?? 0) * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {[
                        { name: "离线", color: "#ff3b30" },
                        { name: "空闲", color: "#34c759" },
                        { name: "充电中", color: "#ff9500" },
                      ].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{
                        background: "#333",
                        border: "1px solid #555",
                        borderRadius: 5,
                        color: "#fff",
                      }}
                    />
                    <Legend wrapperStyle={{ color: "#aaa" }} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ marginTop: 16, fontSize: 12, color: "#aaa" }}>
                  当前状态: <span style={{ color: "#fff", fontWeight: "600" }}>{statusData?.current_status || "未知"}</span>
                </div>
              </ChartCard>
            )}
          </div>
        </div>
      )}

      {/* Error/Loading */}
      {error && (
        <div style={{
          background: configError ? "rgba(255, 193, 7, 0.1)" : "rgba(255, 59, 48, 0.1)",
          border: `2px solid ${configError ? "#ffc107" : "#ff3b30"}`,
          borderRadius: 12,
          padding: 24,
          marginBottom: 24,
          color: configError ? "#ffc107" : "#ff3b30",
        }}>
          <h3 style={{ fontSize: 18, fontWeight: "600", marginBottom: 12 }}>
            {configError ? "⚠️ 配置错误" : "⚠️ 加载失败"}
          </h3>
          <p style={{ marginBottom: 8, lineHeight: 1.6 }}>{error.message}</p>
          {configError ? (
            <div style={{ 
              background: "rgba(0,0,0,0.2)", 
              borderRadius: 8, 
              padding: 16, 
              marginTop: 16,
              fontSize: 14,
            }}>
              <p style={{ marginBottom: 12, fontWeight: "600", color: "#ffc107" }}>
                🔧 生产环境配置修复步骤：
              </p>
              <ol style={{ marginLeft: 20, lineHeight: 2.2 }}>
                <li style={{ marginBottom: 12 }}>
                  <strong>方法1（推荐）：</strong>在服务器上设置环境变量
                  <code style={{ 
                    display: "block", 
                    background: "rgba(0,0,0,0.4)", 
                    padding: "10px 14px", 
                    borderRadius: 4,
                    marginTop: 8,
                    fontFamily: "monospace",
                    fontSize: 13,
                    color: "#4ade80",
                    border: "1px solid rgba(74, 222, 128, 0.3)"
                  }}>
                    export NEXT_PUBLIC_CSMS_HTTP={typeof window !== 'undefined' ? `http://${window.location.hostname}:9000` : 'http://你的服务器IP:9000'}
                  </code>
                  <div style={{ marginTop: 8, fontSize: 12, color: "#aaa" }}>
                    然后重启服务：<code style={{ background: "rgba(0,0,0,0.3)", padding: "2px 6px", borderRadius: 3 }}>docker compose -f docker-compose.prod.yml restart admin</code>
                  </div>
                </li>
                <li style={{ marginBottom: 12 }}>
                  <strong>方法2：</strong>在 docker-compose.prod.yml 中直接设置
                  <code style={{ 
                    display: "block", 
                    background: "rgba(0,0,0,0.4)", 
                    padding: "10px 14px", 
                    borderRadius: 4,
                    marginTop: 8,
                    fontFamily: "monospace",
                    fontSize: 13,
                    color: "#4ade80",
                    border: "1px solid rgba(74, 222, 128, 0.3)"
                  }}>
                    admin:<br/>
                    &nbsp;&nbsp;environment:<br/>
                    &nbsp;&nbsp;&nbsp;&nbsp;- NEXT_PUBLIC_CSMS_HTTP={typeof window !== 'undefined' ? `http://${window.location.hostname}:9000` : 'http://你的服务器IP:9000'}
                  </code>
                </li>
                <li style={{ marginBottom: 12 }}>
                  <strong>方法3：</strong>确保访问URL使用正确的服务器IP
                  <div style={{ marginTop: 8, fontSize: 12, color: "#aaa" }}>
                    当前访问地址：<code style={{ background: "rgba(0,0,0,0.3)", padding: "2px 6px", borderRadius: 3 }}>
                      {typeof window !== 'undefined' ? window.location.href : '未知'}
                    </code>
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#ff6b6b" }}>
                    ❌ 错误：使用占位符（如 your-server-ip）<br/>
                    ✅ 正确：使用实际IP（如 47.236.134.99）
                  </div>
                </li>
              </ol>
              <div style={{ 
                marginTop: 16, 
                padding: 12, 
                background: "rgba(255, 193, 7, 0.1)", 
                borderRadius: 6,
                border: "1px solid rgba(255, 193, 7, 0.3)"
              }}>
                <strong style={{ color: "#ffc107" }}>💡 提示：</strong>
                <div style={{ marginTop: 6, fontSize: 12, color: "#aaa", lineHeight: 1.6 }}>
                  配置完成后，刷新页面即可生效。如果问题仍然存在，请检查：
                  <ul style={{ marginLeft: 20, marginTop: 6 }}>
                    <li>Docker服务是否正常运行</li>
                    <li>9000端口是否已开放</li>
                    <li>防火墙规则是否正确</li>
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <>
              <p style={{ fontSize: 12, color: "#aaa", marginBottom: 12, marginTop: 8 }}>
                API 地址: {apiUrl}
              </p>
              <button
                onClick={() => mutate()}
                style={{
                  padding: "8px 16px",
                  background: "#ff3b30",
                  border: "none",
                  borderRadius: 6,
                  color: "#fff",
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                重试
              </button>
            </>
          )}
        </div>
      )}

      {/* Chargers Grid */}
      {filteredChargers.length === 0 ? (
        <div style={{
          background: "rgba(255,255,255,0.05)",
          borderRadius: 12,
          padding: 48,
          textAlign: "center",
          border: "1px solid rgba(255,255,255,0.1)",
        }}>
          <p style={{ fontSize: 18, color: "#888" }}>暂无充电桩记录</p>
          <p style={{ fontSize: 14, color: "#666", marginTop: 8 }}>
            请运行 <code style={{ background: "rgba(255,255,255,0.1)", padding: "4px 8px", borderRadius: 4 }}>python3 interactive.py</code> 创建充电桩
          </p>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
          gap: 24,
        }}>
          {filteredChargers.map((c: Charger) => {
            const offline = isOffline(c.last_seen);
            const timeAgo = Math.floor((Date.now() - new Date(c.last_seen).getTime()) / 1000);
            return (
              <ChargerCard 
                key={c.id} 
                charger={c} 
                offline={offline} 
                timeAgo={timeAgo} 
                onUpdate={mutate} 
                apiBase={apiBase}
                onShowCharts={() => setSelectedChargerForCharts(c.id)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 16,
      border: `1px solid ${color}40`,
    }}>
      <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: "700", color }}>
        {value}
      </div>
    </div>
  );
}

function FilterTab({ label, count, active, onClick, color }: { label: string; count: number; active: boolean; onClick: () => void; color?: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 16px",
        background: active ? (color || "#007AFF") : "rgba(255,255,255,0.05)",
        border: `1px solid ${active ? (color || "#007AFF") : "rgba(255,255,255,0.2)"}`,
        borderRadius: 8,
        color: active ? "#fff" : "#aaa",
        fontSize: 14,
        fontWeight: active ? "600" : "400",
        cursor: "pointer",
        display: "flex",
        gap: 8,
        alignItems: "center",
      }}
    >
      <span>{label}</span>
      <span style={{
        background: active ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.1)",
        padding: "2px 8px",
        borderRadius: 12,
        fontSize: 12,
      }}>
        {count}
      </span>
    </button>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "rgba(0,0,0,0.2)",
      borderRadius: 8,
      padding: 16,
    }}>
      <h3 style={{ fontSize: 16, fontWeight: "600", marginBottom: 16, color: "#fff" }}>{title}</h3>
      {children}
    </div>
  );
}

function ChargerCard({ charger, offline, timeAgo, onUpdate, apiBase, onShowCharts }: { charger: Charger; offline: boolean; timeAgo: number; onUpdate?: () => void; apiBase: string; onShowCharts?: () => void }) {
  const statusColor = offline ? "#ff3b30" : charger.status === "Charging" ? "#ff9500" : "#34c759";
  const statusText = offline ? "离线" : charger.status;
  const [isEditingPrice, setIsEditingPrice] = useState(false);
  const [priceValue, setPriceValue] = useState<string>(String(charger.price_per_kwh || 2700));
  const [isUpdating, setIsUpdating] = useState(false);
  
  // 当charger数据更新时，同步更新priceValue
  useEffect(() => {
    setPriceValue(String(charger.price_per_kwh || 2700));
  }, [charger.price_per_kwh]);
  
  const handleUpdatePrice = async () => {
    const price = parseFloat(priceValue);
    if (isNaN(price) || price < 0) {
      alert("请输入有效的价格");
      return;
    }
    
    try {
      setIsUpdating(true);
      const res = await fetch(`${apiBase}/api/updatePrice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chargePointId: charger.id,
          pricePerKwh: price,
        }),
      });
      
      if (res.ok) {
        setIsEditingPrice(false);
        // 触发数据刷新
        if (onUpdate) {
          onUpdate();
        } else {
          window.location.reload();
        }
      } else {
        const error = await res.json();
        alert(`更新失败: ${error.detail || "未知错误"}`);
      }
    } catch (error) {
      console.error("Update price failed:", error);
      alert("网络错误，请重试");
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 20,
      border: `1px solid ${statusColor}40`,
      backdropFilter: "blur(10px)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
            <h3 style={{ fontSize: 24, fontWeight: "700" }}>{charger.id}</h3>
            {charger.is_configured !== undefined && (
              <div style={{
                background: charger.is_configured ? "rgba(52,199,89,0.2)" : "rgba(255,149,0,0.2)",
                border: `1px solid ${charger.is_configured ? "#34c759" : "#ff9500"}`,
                borderRadius: 4,
                padding: "2px 8px",
                fontSize: 11,
                fontWeight: "600",
                color: charger.is_configured ? "#34c759" : "#ff9500",
              }}>
                {charger.is_configured ? "已配置" : "未配置"}
              </div>
            )}
          </div>
          <div style={{ fontSize: 14, color: "#aaa" }}>
            {new Date(charger.last_seen).toLocaleString()} • {timeAgo}s ago
          </div>
        </div>
        <div style={{
          background: `${statusColor}20`,
          border: `1px solid ${statusColor}`,
          borderRadius: 8,
          padding: "8px 16px",
          fontSize: 14,
          fontWeight: "600",
          color: statusColor,
        }}>
          {statusText}
        </div>
      </div>
      
      {/* 配置状态提示 */}
      {charger.is_configured === false && (
        <div style={{
          background: "rgba(255,149,0,0.1)",
          border: "1px solid rgba(255,149,0,0.3)",
          borderRadius: 8,
          padding: 12,
          marginBottom: 16,
          fontSize: 13,
          color: "#ff9500",
        }}>
          ⚠️ 此充电桩未完整配置，无法面向用户使用
          {!charger.has_location && <div style={{ marginTop: 4 }}>• 缺少位置信息</div>}
          {!charger.has_pricing && <div style={{ marginTop: 4 }}>• 缺少价格信息</div>}
          <a
            href="/charger-management"
            style={{
              display: "inline-block",
              marginTop: 8,
              color: "#ff9500",
              textDecoration: "underline",
            }}
          >
            前往配置 →
          </a>
        </div>
      )}

      {/* QR Code & Circular Gauge */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-around",
        marginBottom: 20,
        gap: 20,
      }}>
        {/* QR Code */}
        <div style={{
          background: "#fff",
          padding: 8,
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}>
          <QRCodeSVG
            value={charger.id}
            size={100}
            level="H"
            includeMargin={false}
          />
        </div>
        
        {/* Circular Gauge */}
        <div style={{
          width: 100,
          height: 100,
          borderRadius: "50%",
          border: "8px solid rgba(255,255,255,0.1)",
          borderTopColor: charger.status === "Charging" ? "#ff9500" : "#5ac8fa",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 24,
          fontWeight: "700",
        }}>
          <div style={{ textAlign: "center" }}>
            <div>{charger.charging_rate || 7.0}</div>
            <div style={{ fontSize: 12, color: "#aaa", marginTop: 4 }}>kW</div>
          </div>
        </div>
      </div>
      
      {/* QR Code Hint */}
      <div style={{
        fontSize: 12,
        color: "#888",
        textAlign: "center",
        marginBottom: 12,
        padding: 8,
        background: "rgba(255,255,255,0.05)",
        borderRadius: 6,
      }}>
        📱 使用 App 扫码连接此充电桩
      </div>

        {/* Summary */}
        <div style={{
          background: "rgba(0,0,0,0.2)",
          borderRadius: 8,
          padding: 12,
        }}>
          <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>会话信息</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
            <div>
              <span style={{ color: "#888", fontSize: 12 }}>授权</span>
              <div style={{ fontSize: 16, fontWeight: "600" }}>
                {charger.session?.authorized ? "✓" : "✗"}
              </div>
            </div>
            <div>
              <span style={{ color: "#888", fontSize: 12 }}>事务ID</span>
              <div style={{ fontSize: 16, fontWeight: "600" }}>
                {charger.session?.transaction_id ?? "-"}
              </div>
            </div>
          </div>
          
          {/* 查看监控数据按钮 */}
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: 8 }}>
            <a
              href={`/chargers/${charger.id}`}
              style={{
                flex: 1,
                padding: "8px 12px",
                background: "rgba(0,122,255,0.2)",
                border: "1px solid #007AFF",
                borderRadius: 6,
                color: "#007AFF",
                fontSize: 13,
                fontWeight: "600",
                textAlign: "center",
                textDecoration: "none",
              }}
            >
              📊 详细数据
            </a>
            {onShowCharts && (
              <button
                onClick={onShowCharts}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: "rgba(139,92,246,0.2)",
                  border: "1px solid #8b5cf6",
                  borderRadius: 6,
                  color: "#8b5cf6",
                  fontSize: 13,
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                📈 实时图表
              </button>
            )}
          </div>
        {(charger.connector_type || charger.charging_rate) && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.1)" }}>
            <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>充电桩信息</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
              {charger.connector_type && (
                <div>
                  <span style={{ color: "#888", fontSize: 12 }}>充电头类型</span>
                  <div style={{ fontSize: 16, fontWeight: "600" }}>
                    {charger.connector_type}
                  </div>
                </div>
              )}
              {charger.charging_rate && (
                <div>
                  <span style={{ color: "#888", fontSize: 12 }}>充电速率</span>
                  <div style={{ fontSize: 16, fontWeight: "600" }}>
                    {charger.charging_rate} kW
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {/* 价格设置 - 始终显示 */}
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>电价设置</div>
          {isEditingPrice ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="number"
                value={priceValue}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPriceValue(e.target.value)}
                placeholder="价格"
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: "rgba(0,0,0,0.3)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 6,
                  color: "#fff",
                  fontSize: 14,
                }}
                disabled={isUpdating}
              />
              <span style={{ fontSize: 14, color: "#aaa" }}>COP/kWh</span>
              <button
                onClick={handleUpdatePrice}
                disabled={isUpdating}
                style={{
                  padding: "8px 16px",
                  background: "#34c759",
                  border: "none",
                  borderRadius: 6,
                  color: "#fff",
                  fontSize: 14,
                  fontWeight: "600",
                  cursor: isUpdating ? "not-allowed" : "pointer",
                  opacity: isUpdating ? 0.6 : 1,
                }}
              >
                {isUpdating ? "保存中..." : "保存"}
              </button>
              <button
                onClick={() => {
                  setIsEditingPrice(false);
                  setPriceValue(String(charger.price_per_kwh || 2700));
                }}
                disabled={isUpdating}
                style={{
                  padding: "8px 16px",
                  background: "rgba(255,255,255,0.1)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 6,
                  color: "#fff",
                  fontSize: 14,
                  fontWeight: "600",
                  cursor: isUpdating ? "not-allowed" : "pointer",
                }}
              >
                取消
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ color: "#888", fontSize: 12 }}>每度电价格</span>
                <div style={{ fontSize: 16, fontWeight: "600" }}>
                  {charger.price_per_kwh || 2700} COP/kWh
                </div>
              </div>
              <button
                onClick={() => {
                  setIsEditingPrice(true);
                  setPriceValue(String(charger.price_per_kwh || 2700));
                }}
                style={{
                  padding: "6px 12px",
                  background: "rgba(0,122,255,0.2)",
                  border: "1px solid #007AFF",
                  borderRadius: 6,
                  color: "#007AFF",
                  fontSize: 12,
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                编辑
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}



