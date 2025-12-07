/**
 * 本文件为 /map 页面：充电桩地图视图。
 * 使用 SWR 每 3s 拉取状态，显示充电桩位置。
 * 使用 react-leaflet 接入真实地图。
 * 支持点击地图添加充电桩位置。
 * 仅用于本地测试与演示。
 */

"use client";

import React, { useState } from "react";
import useSWR from "swr";
import dynamic from "next/dynamic";

// 动态导入 Leaflet 组件（仅客户端）
const MapContainer = dynamic(
  () => import("react-leaflet").then((mod) => mod.MapContainer),
  { ssr: false }
);
const TileLayer = dynamic(
  () => import("react-leaflet").then((mod) => mod.TileLayer),
  { ssr: false }
);
const Marker = dynamic(
  () => import("react-leaflet").then((mod) => mod.Marker),
  { ssr: false }
);
const Popup = dynamic(
  () => import("react-leaflet").then((mod) => mod.Popup),
  { ssr: false }
);
const useMapEvents = dynamic(
  () => import("react-leaflet").then((mod) => mod.useMapEvents),
  { ssr: false }
);

// 导入 Leaflet CSS
import "leaflet/dist/leaflet.css";

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
};

const fetcher = async (url: string): Promise<Charger[]> => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

// 用于处理地图点击事件的组件
function MapClickHandler({ onClick }: { onClick: (latlng: { lat: number; lng: number }) => void }) {
  const map = (useMapEvents as any)({
    click: (e: any) => {
      onClick({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

export default function MapPage() {
  const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";
  const { data: chargers = [], error, isLoading, mutate } = useSWR<Charger[]>(
    `${apiBase}/chargers`,
    fetcher,
    { refreshInterval: 3000 }
  );

  const [selectedCharger, setSelectedCharger] = useState<Charger | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [clickedPos, setClickedPos] = useState<{ lat: number; lng: number } | null>(null);
  const [newChargerId, setNewChargerId] = useState("");
  const [newAddress, setNewAddress] = useState("");
  const [adding, setAdding] = useState(false);

  const chargersWithLocation = chargers.filter(c => c.location?.latitude && c.location?.longitude);

  const isOffline = (lastSeen: string) => {
    const last = new Date(lastSeen).getTime();
    const now = Date.now();
    return now - last > 30000;
  };

  const getStatusColor = (status: string, offline: boolean) => {
    if (offline) return "#ff3b30";
    switch (status) {
      case "Available": return "#34c759";
      case "Charging": return "#ff9500";
      case "Faulted": return "#ff3b30";
      default: return "#8b5cf6";
    }
  };

  // 计算地图中心点
  const center = chargersWithLocation.length > 0 
    ? {
        lat: chargersWithLocation.reduce((sum, c) => sum + (c.location?.latitude || 0), 0) / chargersWithLocation.length,
        lng: chargersWithLocation.reduce((sum, c) => sum + (c.location?.longitude || 0), 0) / chargersWithLocation.length,
      }
    : { lat: 4.6110, lng: -74.0708 }; // 默认波哥大

  const handleMapClick = (latlng: { lat: number; lng: number }) => {
    if (!isAdding) {
      setSelectedCharger(null);
      return;
    }
    setClickedPos(latlng);
  };

  const handleAddCharger = async () => {
    if (!newChargerId.trim() || !clickedPos) {
      alert("请输入充电桩ID");
      return;
    }

    try {
      setAdding(true);

      const res = await fetch(`${apiBase}/api/updateLocation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chargePointId: newChargerId.trim(),
          latitude: clickedPos.lat,
          longitude: clickedPos.lng,
          address: newAddress || "",
        }),
      });

      if (res.ok) {
        alert("充电桩位置已添加");
        setIsAdding(false);
        setClickedPos(null);
        setNewChargerId("");
        setNewAddress("");
        await mutate();
      } else {
        alert("添加失败");
      }
    } catch (error) {
      console.error("Add charger failed:", error);
      alert("网络错误");
    } finally {
      setAdding(false);
    }
  };

  if (isLoading) {
    return (
      <div style={{
        height: "100vh",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        color: "#fff",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        fontFamily: "ui-sans-serif, system-ui",
      }}>
        <div style={{ fontSize: 18 }}>加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        height: "100vh",
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        color: "#ff3b30",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        fontFamily: "ui-sans-serif, system-ui",
      }}>
        <div style={{ fontSize: 18 }}>加载失败: {error.message}</div>
      </div>
    );
  }

  return (
    <div style={{
      height: "100vh",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
      color: "#fff",
      fontFamily: "ui-sans-serif, system-ui",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{ padding: 20, borderBottom: "1px solid #2a2a3e" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h1 style={{ fontSize: 28, fontWeight: "700", color: "#fff", margin: 0 }}>
            🗺️ 充电桩地图
          </h1>
          <button
            onClick={() => setIsAdding(!isAdding)}
            style={{
              background: isAdding ? "#ff3b30" : "#34c759",
              border: "none",
              borderRadius: 8,
              padding: "10px 20px",
              color: "#fff",
              fontSize: 14,
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            {isAdding ? "✕ 取消添加" : "➕ 添加充电桩"}
          </button>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 14, color: "#aaa" }}>
          <span>实时刷新: 3秒</span>
          <span>•</span>
          <span>标记点: {chargersWithLocation.length}</span>
          {isAdding && <span style={{ color: "#34c759" }}>• 点击地图添加位置</span>}
        </div>
      </div>

      {/* 地图容器 */}
      <div style={{ flex: 1, position: "relative" }}>
        <div style={{ position: "relative", width: "100%", height: "100%" }}>
          {(MapContainer as any) && (TileLayer as any) && (Marker as any) && (Popup as any) ? (
            <MapContainer
              center={[center.lat, center.lng]}
              zoom={13}
              style={{ height: "100%", width: "100%" }}
              scrollWheelZoom={true}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              
              {/* 地图点击处理器 */}
              <MapClickHandler onClick={handleMapClick} />

              {/* 充电桩标记点 */}
              {chargersWithLocation.map((charger) => {
                const offline = isOffline(charger.last_seen);
                const statusColor = getStatusColor(charger.status, offline);

                return (
                  <Marker
                    key={charger.id}
                    position={[
                      charger.location?.latitude || 0,
                      charger.location?.longitude || 0,
                    ]}
                  >
                    <Popup>
                      <div style={{ color: "#333", minWidth: 150 }}>
                        <div style={{ fontWeight: "700", fontSize: 16, marginBottom: 8 }}>
                          {charger.id}
                        </div>
                        <div style={{ fontSize: 14, marginBottom: 4 }}>
                          <strong>状态:</strong> {offline ? "离线" : charger.status}
                        </div>
                        <div style={{ fontSize: 14, marginBottom: 4 }}>
                          <strong>地址:</strong> {charger.location?.address || "N/A"}
                        </div>
                        <div style={{ fontSize: 14, marginBottom: 4 }}>
                          <strong>电量:</strong> {charger.session.meter} Wh
                        </div>
                        <div style={{ fontSize: 14, marginBottom: 4 }}>
                          <strong>事务ID:</strong> {charger.session.transaction_id?.toString() || "-"}
                        </div>
                        {charger.connector_type && (
                          <div style={{ fontSize: 14, marginBottom: 4 }}>
                            <strong>充电头类型:</strong> {charger.connector_type}
                          </div>
                        )}
                        {charger.charging_rate && (
                          <div style={{ fontSize: 14 }}>
                            <strong>充电速率:</strong> {charger.charging_rate} kW
                          </div>
                        )}
                      </div>
                    </Popup>
                  </Marker>
                );
              })}

              {/* 点击位置的标记（添加模式） */}
              {clickedPos && isAdding && (
                <Marker position={[clickedPos.lat, clickedPos.lng]} icon={undefined as any}>
                  <Popup>
                    <div style={{ color: "#007AFF", fontWeight: "700" }}>
                      新充电桩位置
                    </div>
                  </Popup>
                </Marker>
              )}
            </MapContainer>
          ) : (
            <div style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "#aaa",
            }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🗺️</div>
              <div style={{ fontSize: 18, marginBottom: 8 }}>正在加载地图...</div>
            </div>
          )}

          {/* 图例 */}
          {!isAdding && (
            <div style={{
              position: "absolute",
              bottom: 20,
              left: 20,
              background: "rgba(26, 26, 46, 0.95)",
              borderRadius: 8,
              padding: 16,
              border: "1px solid #2a2a3e",
              zIndex: 1000,
            }}>
              <div style={{ fontSize: 14, fontWeight: "600", marginBottom: 8 }}>图例</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <LegendItem color="#34c759" label="可用" />
                <LegendItem color="#ff9500" label="充电中" />
                <LegendItem color="#ff3b30" label="故障/离线" />
              </div>
            </div>
          )}

          {/* 添加充电桩表单 */}
          {clickedPos && isAdding && (
            <div style={{
              position: "absolute",
              top: 20,
              right: 20,
              width: 300,
              background: "rgba(26, 26, 46, 0.95)",
              borderRadius: 12,
              padding: 20,
              border: "2px solid #007AFF",
              backdropFilter: "blur(10px)",
              zIndex: 1000,
            }}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 14, color: "#aaa", marginBottom: 8 }}>
                  充电桩ID
                </label>
                <input
                  type="text"
                  value={newChargerId}
                  onChange={(e) => setNewChargerId(e.target.value)}
                  placeholder="例如: CP-NEW-001"
                  style={{
                    width: "100%",
                    padding: 12,
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 14, color: "#aaa", marginBottom: 8 }}>
                  地址（可选）
                </label>
                <input
                  type="text"
                  value={newAddress}
                  onChange={(e) => setNewAddress(e.target.value)}
                  placeholder="例如: 波哥大市中心"
                  style={{
                    width: "100%",
                    padding: 12,
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handleAddCharger}
                  disabled={adding || !newChargerId.trim()}
                  style={{
                    flex: 1,
                    padding: 12,
                    background: adding || !newChargerId.trim() ? "#666" : "#007AFF",
                    border: "none",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: "600",
                    cursor: adding || !newChargerId.trim() ? "not-allowed" : "pointer",
                  }}
                >
                  {adding ? "添加中..." : "确认添加"}
                </button>
                <button
                  onClick={() => {
                    setClickedPos(null);
                    setNewChargerId("");
                    setNewAddress("");
                  }}
                  disabled={adding}
                  style={{
                    flex: 1,
                    padding: 12,
                    background: "rgba(255,255,255,0.1)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: "600",
                    cursor: adding ? "not-allowed" : "pointer",
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 16,
        height: 16,
        borderRadius: "50%",
        backgroundColor: color,
        border: "2px solid #fff",
      }} />
      <span style={{ fontSize: 14 }}>{label}</span>
    </div>
  );
}

