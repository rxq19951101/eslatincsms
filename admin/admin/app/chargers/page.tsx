/**
 * 本文件为 /chargers 页面：充电桩监测大屏视图。
 * 使用 SWR 每 3s 拉取状态，暗色主题、圆环仪表、统计卡片。
 * 仅用于本地测试与演示。
 */

"use client";

import React, { useState, useEffect } from "react";
import useSWR from "swr";
import { QRCodeSVG } from "qrcode.react";

type Charger = {
  id: string;
  status: string;
  last_seen: string;
  location?: {
    latitude: number | null;
    longitude: number | null;
    address: string;
  };
  session: {
    authorized: boolean;
    transaction_id: number | null;
    meter: number;
  };
  connector_type?: string;  // 充电头类型: GBT, Type1, Type2, CCS1, CCS2
  charging_rate?: number;  // 充电速率 (kW)
  price_per_kwh?: number;  // 每度电价格 (COP/kWh)
};

const fetcher = async (url: string): Promise<Charger[]> => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export default function ChargersPage() {
  const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";
  const { data: chargers = [], error, isLoading, mutate } = useSWR<Charger[]>(
    `${apiBase}/chargers`,
    fetcher,
    { refreshInterval: 3000 }
  );

  const isOffline = (lastSeen: string) => {
    const last = new Date(lastSeen).getTime();
    const now = Date.now();
    return now - last > 30000;
  };

  const stats = {
    total: chargers.length,
    online: chargers.filter((c) => !isOffline(c.last_seen)).length,
    available: chargers.filter((c) => !isOffline(c.last_seen) && c.status === "Available").length,
    charging: chargers.filter((c) => !isOffline(c.last_seen) && c.status === "Charging").length,
    offline: chargers.filter((c) => isOffline(c.last_seen)).length,
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
        <div style={{ display: "flex", gap: 16, fontSize: 14, color: "#aaa" }}>
          <span>OCPP 1.6J Test Platform</span>
          <span>•</span>
          <span>实时刷新: 3秒</span>
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
        <StatCard label="在线" value={stats.online} color="#34c759" />
        <StatCard label="可用" value={stats.available} color="#5ac8fa" />
        <StatCard label="充电中" value={stats.charging} color="#ff9500" />
        <StatCard label="离线" value={stats.offline} color="#ff3b30" />
      </div>

      {/* Error/Loading */}
      {error && (
        <div style={{
          background: "rgba(255,59,48,0.2)",
          border: "1px solid #ff3b30",
          borderRadius: 8,
          padding: 16,
          marginBottom: 24,
        }}>
          加载失败: {error.message}
        </div>
      )}

      {/* Chargers Grid */}
      {chargers.length === 0 ? (
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
          {chargers.map((c) => {
            const offline = isOffline(c.last_seen);
            const timeAgo = Math.floor((Date.now() - new Date(c.last_seen).getTime()) / 1000);
            return <ChargerCard key={c.id} charger={c} offline={offline} timeAgo={timeAgo} onUpdate={mutate} />;
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

function ChargerCard({ charger, offline, timeAgo, onUpdate }: { charger: Charger; offline: boolean; timeAgo: number; onUpdate?: () => void }) {
  const statusColor = offline ? "#ff3b30" : charger.status === "Charging" ? "#ff9500" : "#34c759";
  const statusText = offline ? "离线" : charger.status;
  const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";
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
          <h3 style={{ fontSize: 24, fontWeight: "700", marginBottom: 4 }}>{charger.id}</h3>
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
              {charger.session.authorized ? "✓" : "✗"}
            </div>
          </div>
          <div>
            <span style={{ color: "#888", fontSize: 12 }}>事务ID</span>
            <div style={{ fontSize: 16, fontWeight: "600" }}>
              {charger.session.transaction_id ?? "-"}
            </div>
          </div>
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
                onChange={(e) => setPriceValue(e.target.value)}
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


