/**
 * 新充电桩管理页面
 * 检测、录入、配置新充电桩
 */

"use client";

import React, { useState, useEffect } from "react";
import useSWR from "swr";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";

type PendingCharger = {
  charger_id: string;
  is_connected: boolean;
  is_configured: boolean;
  status: string;
  last_seen: string | null;
  vendor: string | null;
  model: string | null;
  has_location: boolean;
  has_pricing: boolean;
};

type ChargerFormData = {
  charger_id: string;
  vendor: string;
  model: string;
  serial_number: string;
  firmware_version: string;
  connector_type: string;
  charging_rate: number;
  latitude: string;
  longitude: string;
  address: string;
  price_per_kwh: number;
};

const fetcher = async (url: string) => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export default function ChargerManagementPage() {
  const [selectedCharger, setSelectedCharger] = useState<PendingCharger | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<ChargerFormData>({
    charger_id: "",
    vendor: "",
    model: "",
    serial_number: "",
    firmware_version: "",
    connector_type: "Type2",
    charging_rate: 7.0,
    latitude: "",
    longitude: "",
    address: "",
    price_per_kwh: 2700.0,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // 获取待配置的充电桩列表
  const { data: pendingChargers = [], error, mutate } = useSWR<PendingCharger[]>(
    `${apiBase}/api/v1/charger-management/pending`,
    fetcher,
    { refreshInterval: 5000 }
  );

  // 当选择充电桩时，填充表单
  useEffect(() => {
    if (selectedCharger) {
      setFormData(prev => ({
        ...prev,
        charger_id: selectedCharger.charger_id,
        vendor: selectedCharger.vendor || "",
        model: selectedCharger.model || "",
        connector_type: "Type2",
        charging_rate: 7.0,
        price_per_kwh: 2700.0,
      }));
      setShowForm(true);
    }
  }, [selectedCharger]);

  const handleInputChange = (field: keyof ChargerFormData, value: string | number) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleCreateCharger = async () => {
    if (!formData.charger_id) {
      alert("请输入充电桩ID");
      return;
    }

    setIsSubmitting(true);
    setSuccessMessage(null);

    try {
      // 创建充电桩记录
      const createRes = await fetch(`${apiBase}/api/v1/charger-management/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          charger_id: formData.charger_id,
          vendor: formData.vendor || null,
          model: formData.model || null,
          serial_number: formData.serial_number || null,
          firmware_version: formData.firmware_version || null,
          connector_type: formData.connector_type,
          charging_rate: formData.charging_rate,
          latitude: formData.latitude ? parseFloat(formData.latitude) : null,
          longitude: formData.longitude ? parseFloat(formData.longitude) : null,
          address: formData.address || null,
          price_per_kwh: formData.price_per_kwh,
        }),
      });

      if (!createRes.ok) {
        const error = await createRes.json();
        throw new Error(error.detail || "创建失败");
      }

      setSuccessMessage("充电桩已成功录入！");
      
      // 刷新列表
      mutate();
      
      // 2秒后重置表单
      setTimeout(() => {
        setShowForm(false);
        setSelectedCharger(null);
        setSuccessMessage(null);
      }, 2000);

    } catch (error: any) {
      alert(`录入失败: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdateLocation = async (chargerId: string, lat: string, lng: string, address: string) => {
    if (!lat || !lng) {
      alert("请输入经纬度");
      return;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/charger-management/location`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          charger_id: chargerId,
          latitude: parseFloat(lat),
          longitude: parseFloat(lng),
          address: address || "",
        }),
      });

      if (res.ok) {
        alert("位置已更新");
        mutate();
      } else {
        const error = await res.json();
        alert(`更新失败: ${error.detail}`);
      }
    } catch (error: any) {
      alert(`更新失败: ${error.message}`);
    }
  };

  const handleUpdatePricing = async (chargerId: string, price: number, rate?: number) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/charger-management/pricing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          charger_id: chargerId,
          price_per_kwh: price,
          charging_rate: rate,
        }),
      });

      if (res.ok) {
        alert("价格已更新");
        mutate();
      } else {
        const error = await res.json();
        alert(`更新失败: ${error.detail}`);
      }
    } catch (error: any) {
      alert(`更新失败: ${error.message}`);
    }
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
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: "700", marginBottom: 8, color: "#fff" }}>
            新充电桩管理
          </h1>
          <div style={{ fontSize: 14, color: "#aaa" }}>
            检测、录入和配置新接入的充电桩
          </div>
        </div>
        <Link href="/chargers" style={{
          padding: "10px 20px",
          background: "rgba(255,255,255,0.1)",
          borderRadius: 8,
          color: "#fff",
          textDecoration: "none",
          fontSize: 14,
        }}>
          ← 返回监测中心
        </Link>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div style={{
          background: "rgba(52,199,89,0.2)",
          border: "1px solid #34c759",
          borderRadius: 8,
          padding: 16,
          marginBottom: 24,
          color: "#34c759",
        }}>
          ✓ {successMessage}
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div style={{
          background: "rgba(255,59,48,0.2)",
          border: "1px solid #ff3b30",
          borderRadius: 8,
          padding: 16,
          marginBottom: 24,
          color: "#ff3b30",
        }}>
          加载失败: {error.message}
        </div>
      )}

      {/* 待配置充电桩列表 */}
      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 20, fontWeight: "600", marginBottom: 16 }}>
          待配置充电桩 ({pendingChargers.length})
        </h2>
        
        {pendingChargers.length === 0 ? (
          <div style={{
            background: "rgba(255,255,255,0.05)",
            borderRadius: 12,
            padding: 48,
            textAlign: "center",
            border: "1px solid rgba(255,255,255,0.1)",
          }}>
            <p style={{ fontSize: 18, color: "#888" }}>暂无待配置的充电桩</p>
            <p style={{ fontSize: 14, color: "#666", marginTop: 8 }}>
              当有新充电桩连接时，会显示在这里
            </p>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(350px, 1fr))",
            gap: 16,
          }}>
            {pendingChargers.map((charger) => (
              <PendingChargerCard
                key={charger.charger_id}
                charger={charger}
                onSelect={() => setSelectedCharger(charger)}
                onUpdateLocation={handleUpdateLocation}
                onUpdatePricing={handleUpdatePricing}
              />
            ))}
          </div>
        )}
      </div>

      {/* 充电桩录入表单 */}
      {showForm && selectedCharger && (
        <div style={{
          background: "rgba(255,255,255,0.05)",
          borderRadius: 12,
          padding: 24,
          border: "1px solid rgba(255,255,255,0.1)",
          marginBottom: 32,
        }}>
          <h2 style={{ fontSize: 20, fontWeight: "600", marginBottom: 20 }}>
            录入充电桩: {selectedCharger.charger_id}
          </h2>
          
          <ChargerForm
            formData={formData}
            onChange={handleInputChange}
            onSubmit={handleCreateCharger}
            onCancel={() => {
              setShowForm(false);
              setSelectedCharger(null);
            }}
            isSubmitting={isSubmitting}
          />
        </div>
      )}
    </div>
  );
}

function PendingChargerCard({
  charger,
  onSelect,
  onUpdateLocation,
  onUpdatePricing,
}: {
  charger: PendingCharger;
  onSelect: () => void;
  onUpdateLocation: (id: string, lat: string, lng: string, address: string) => void;
  onUpdatePricing: (id: string, price: number, rate?: number) => void;
}) {
  const [isEditingLocation, setIsEditingLocation] = useState(false);
  const [isEditingPricing, setIsEditingPricing] = useState(false);
  const [locationData, setLocationData] = useState({
    lat: "",
    lng: "",
    address: "",
  });
  const [pricingData, setPricingData] = useState({
    price: "2700",
    rate: "7.0",
  });

  const getStatusBadge = () => {
    if (!charger.has_location && !charger.has_pricing) {
      return { text: "待配置", color: "#ff9500" };
    } else if (!charger.has_location) {
      return { text: "待设置位置", color: "#5ac8fa" };
    } else if (!charger.has_pricing) {
      return { text: "待设置价格", color: "#ff9500" };
    } else {
      return { text: "已配置", color: "#34c759" };
    }
  };

  const badge = getStatusBadge();

  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 20,
      border: `1px solid ${badge.color}40`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ fontSize: 20, fontWeight: "700" }}>{charger.charger_id}</h3>
        <div style={{
          background: `${badge.color}20`,
          border: `1px solid ${badge.color}`,
          borderRadius: 6,
          padding: "4px 12px",
          fontSize: 12,
          color: badge.color,
        }}>
          {badge.text}
        </div>
      </div>

      {/* 基本信息 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "#aaa", marginBottom: 4 }}>状态</div>
        <div style={{ fontSize: 14, color: "#fff" }}>{charger.status}</div>
        {charger.vendor && (
          <>
            <div style={{ fontSize: 12, color: "#aaa", marginTop: 8, marginBottom: 4 }}>厂商</div>
            <div style={{ fontSize: 14, color: "#fff" }}>{charger.vendor}</div>
          </>
        )}
        {charger.model && (
          <>
            <div style={{ fontSize: 12, color: "#aaa", marginTop: 8, marginBottom: 4 }}>型号</div>
            <div style={{ fontSize: 14, color: "#fff" }}>{charger.model}</div>
          </>
        )}
      </div>

      {/* 配置状态 */}
      <div style={{
        background: "rgba(0,0,0,0.2)",
        borderRadius: 8,
        padding: 12,
        marginBottom: 16,
      }}>
        <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>配置状态</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <ConfigItem
            label="位置"
            configured={charger.has_location}
            isEditing={isEditingLocation}
            onEdit={() => setIsEditingLocation(true)}
            onCancel={() => setIsEditingLocation(false)}
            onSave={() => {
              onUpdateLocation(charger.charger_id, locationData.lat, locationData.lng, locationData.address);
              setIsEditingLocation(false);
            }}
          >
            {isEditingLocation ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <input
                  type="number"
                  placeholder="纬度"
                  value={locationData.lat}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLocationData(prev => ({ ...prev, lat: e.target.value }))}
                  style={{
                    padding: "6px 10px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 6,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
                <input
                  type="number"
                  placeholder="经度"
                  value={locationData.lng}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLocationData(prev => ({ ...prev, lng: e.target.value }))}
                  style={{
                    padding: "6px 10px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 6,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
                <input
                  type="text"
                  placeholder="地址"
                  value={locationData.address}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLocationData(prev => ({ ...prev, address: e.target.value }))}
                  style={{
                    padding: "6px 10px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 6,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
              </div>
            ) : (
              <span style={{ color: charger.has_location ? "#34c759" : "#888" }}>
                {charger.has_location ? "✓ 已设置" : "✗ 未设置"}
              </span>
            )}
          </ConfigItem>
          
          <ConfigItem
            label="定价"
            configured={charger.has_pricing}
            isEditing={isEditingPricing}
            onEdit={() => setIsEditingPricing(true)}
            onCancel={() => setIsEditingPricing(false)}
            onSave={() => {
              onUpdatePricing(charger.charger_id, parseFloat(pricingData.price), parseFloat(pricingData.rate));
              setIsEditingPricing(false);
            }}
          >
            {isEditingPricing ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <input
                  type="number"
                  placeholder="价格 (COP/kWh)"
                  value={pricingData.price}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPricingData(prev => ({ ...prev, price: e.target.value }))}
                  style={{
                    padding: "6px 10px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 6,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
                <input
                  type="number"
                  placeholder="充电速率 (kW)"
                  value={pricingData.rate}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPricingData(prev => ({ ...prev, rate: e.target.value }))}
                  style={{
                    padding: "6px 10px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 6,
                    color: "#fff",
                    fontSize: 14,
                  }}
                />
              </div>
            ) : (
              <span style={{ color: charger.has_pricing ? "#34c759" : "#888" }}>
                {charger.has_pricing ? "✓ 已设置" : "✗ 未设置"}
              </span>
            )}
          </ConfigItem>
        </div>
      </div>

      {/* 操作按钮 */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={onSelect}
          style={{
            flex: 1,
            padding: "10px",
            background: "#007AFF",
            border: "none",
            borderRadius: 6,
            color: "#fff",
            fontSize: 14,
            fontWeight: "600",
            cursor: "pointer",
          }}
        >
          完整录入
        </button>
      </div>
    </div>
  );
}

function ConfigItem({
  label,
  configured,
  isEditing,
  onEdit,
  onCancel,
  onSave,
  children,
}: {
  label: string;
  configured: boolean;
  isEditing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ fontSize: 12, color: "#aaa" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, justifyContent: "flex-end" }}>
        {children}
        {!isEditing && !configured && (
          <button
            onClick={onEdit}
            style={{
              padding: "4px 12px",
              background: "rgba(0,122,255,0.2)",
              border: "1px solid #007AFF",
              borderRadius: 6,
              color: "#007AFF",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            设置
          </button>
        )}
        {isEditing && (
          <>
            <button
              onClick={onSave}
              style={{
                padding: "4px 12px",
                background: "#34c759",
                border: "none",
                borderRadius: 6,
                color: "#fff",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              保存
            </button>
            <button
              onClick={onCancel}
              style={{
                padding: "4px 12px",
                background: "rgba(255,255,255,0.1)",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 6,
                color: "#fff",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              取消
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function ChargerForm({
  formData,
  onChange,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  formData: ChargerFormData;
  onChange: (field: keyof ChargerFormData, value: string | number) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
        <FormField
          label="充电桩ID"
          value={formData.charger_id}
          onChange={(v) => onChange("charger_id", v)}
          required
          disabled
        />
        <FormField
          label="厂商"
          value={formData.vendor}
          onChange={(v) => onChange("vendor", v)}
        />
        <FormField
          label="型号"
          value={formData.model}
          onChange={(v) => onChange("model", v)}
        />
        <FormField
          label="序列号"
          value={formData.serial_number}
          onChange={(v) => onChange("serial_number", v)}
        />
        <FormField
          label="固件版本"
          value={formData.firmware_version}
          onChange={(v) => onChange("firmware_version", v)}
        />
        <FormField
          label="连接器类型"
          value={formData.connector_type}
          onChange={(v) => onChange("connector_type", v)}
          type="select"
          options={["Type2", "GBT", "Type1", "CCS1", "CCS2"]}
        />
        <FormField
          label="充电速率 (kW)"
          value={String(formData.charging_rate)}
          onChange={(v) => onChange("charging_rate", parseFloat(v))}
          type="number"
        />
        <FormField
          label="价格 (COP/kWh)"
          value={String(formData.price_per_kwh)}
          onChange={(v) => onChange("price_per_kwh", parseFloat(v))}
          type="number"
          required
        />
      </div>

      <div>
        <h3 style={{ fontSize: 16, fontWeight: "600", marginBottom: 12 }}>位置信息</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
          <FormField
            label="纬度"
            value={formData.latitude}
            onChange={(v) => onChange("latitude", v)}
            type="number"
            required
          />
          <FormField
            label="经度"
            value={formData.longitude}
            onChange={(v) => onChange("longitude", v)}
            type="number"
            required
          />
        </div>
        <FormField
          label="地址"
          value={formData.address}
          onChange={(v) => onChange("address", v)}
          type="textarea"
        />
      </div>

      <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
        <button
          onClick={onCancel}
          disabled={isSubmitting}
          style={{
            padding: "12px 24px",
            background: "rgba(255,255,255,0.1)",
            border: "1px solid rgba(255,255,255,0.2)",
            borderRadius: 8,
            color: "#fff",
            fontSize: 14,
            fontWeight: "600",
            cursor: isSubmitting ? "not-allowed" : "pointer",
          }}
        >
          取消
        </button>
        <button
          onClick={onSubmit}
          disabled={isSubmitting}
          style={{
            padding: "12px 24px",
            background: isSubmitting ? "rgba(52,199,89,0.6)" : "#34c759",
            border: "none",
            borderRadius: 8,
            color: "#fff",
            fontSize: 14,
            fontWeight: "600",
            cursor: isSubmitting ? "not-allowed" : "pointer",
          }}
        >
          {isSubmitting ? "提交中..." : "提交录入"}
        </button>
      </div>
    </div>
  );
}

function FormField({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  disabled = false,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "number" | "select" | "textarea";
  required?: boolean;
  disabled?: boolean;
  options?: string[];
}) {
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    background: disabled ? "rgba(0,0,0,0.2)" : "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.2)",
    borderRadius: 6,
    color: "#fff",
    fontSize: 14,
    fontFamily: "inherit",
  };

  return (
    <div>
      <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 6 }}>
        {label} {required && <span style={{ color: "#ff3b30" }}>*</span>}
      </label>
      {type === "select" && options ? (
        <select
          value={value}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
          style={inputStyle}
          disabled={disabled}
        >
          {options.map(opt => (
            <option key={opt} value={opt} style={{ background: "#1a1a2e", color: "#fff" }}>
              {opt}
            </option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea
          value={value}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
          style={{ ...inputStyle, minHeight: 80, resize: "vertical" }}
          disabled={disabled}
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          style={inputStyle}
          required={required}
          disabled={disabled}
          step={type === "number" ? "any" : undefined}
        />
      )}
    </div>
  );
}

