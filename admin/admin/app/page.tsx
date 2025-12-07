/**
 * 本文件为 admin 首页：提供导航入口。
 * 仅用于本地测试与演示。
 */

"use client";

import React from "react";
import Link from "next/link";

export default function HomePage() {
  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
      color: "#fff",
      padding: 40,
      fontFamily: "ui-sans-serif, system-ui",
    }}>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>
        <h1 style={{ fontSize: 36, fontWeight: "700", marginBottom: 8 }}>
          OCPP 充电管理平台
        </h1>
        <p style={{ fontSize: 18, color: "#aaa", marginBottom: 48 }}>
          本地测试与演示环境
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20 }}>
          <FeatureCard
            icon="🗺️"
            title="地图视图"
            description="实时查看所有充电桩的位置和状态"
            link="/map"
          />
          <FeatureCard
            icon="🔌"
            title="监测中心"
            description="充电桩实时状态大屏展示"
            link="/chargers"
          />
          <FeatureCard
            icon="💬"
            title="客服消息"
            description="查看和回复用户消息"
            link="/messages"
          />
        </div>

        <div style={{ marginTop: 60, padding: 24, backgroundColor: "rgba(255,255,255,0.05)", borderRadius: 12 }}>
          <h2 style={{ fontSize: 20, fontWeight: "600", marginBottom: 16 }}>快速开始</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <QuickStartStep number="1" text="运行充电桩模拟器：python3 interactive.py --id CP-001 --lat 39.9 --lng 116.4" />
            <QuickStartStep number="2" text="在地图视图查看充电桩位置" />
            <QuickStartStep number="3" text="在监测中心查看实时状态" />
            <QuickStartStep number="4" text="使用 App 扫码开始充电" />
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description, link }: { icon: string; title: string; description: string; link: string }) {
  return (
    <Link href={link} style={{ textDecoration: "none" }}>
      <div style={{
        background: "rgba(255,255,255,0.05)",
        borderRadius: 12,
        padding: 24,
        border: "1px solid rgba(255,255,255,0.1)",
        transition: "all 0.2s",
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.08)";
        e.currentTarget.style.borderColor = "#007AFF";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.05)";
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
      }}
      >
        <div style={{ fontSize: 48, marginBottom: 16 }}>{icon}</div>
        <h3 style={{ fontSize: 20, fontWeight: "600", marginBottom: 8, color: "#fff" }}>{title}</h3>
        <p style={{ fontSize: 14, color: "#aaa", lineHeight: 1.6 }}>{description}</p>
      </div>
    </Link>
  );
}

function QuickStartStep({ number, text }: { number: string; text: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{
        width: 32,
        height: 32,
        borderRadius: "50%",
        backgroundColor: "#007AFF",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 16,
        fontWeight: "700",
      }}>
        {number}
      </div>
      <span style={{ fontSize: 14, color: "#ddd" }}>{text}</span>
    </div>
  );
}



