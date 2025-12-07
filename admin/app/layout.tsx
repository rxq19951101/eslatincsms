/**
 * 本文件定义 admin 应用的根布局，包含基础 HTML 结构与全局样式占位。
 * 使用 Next.js App Router，所有页面共享该布局。
 * 仅用于本地测试与演示。
 */

"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="robots" content="noindex, nofollow" />
      </head>
      <body style={{ fontFamily: "ui-sans-serif, system-ui", margin: 0, padding: 0 }}>
        <noscript>请启用 JavaScript</noscript>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          {/* 侧边导航栏 */}
          <nav style={{
            width: 200,
            backgroundColor: "#1a1a2e",
            borderRight: "1px solid #2a2a3e",
            padding: 20,
          }}>
            <h2 style={{ color: "#fff", fontSize: 24, fontWeight: "700", marginBottom: 24 }}>
              OCPP Admin
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <NavLink href="/" pathname={pathname} icon="🏠" label="首页" />
              <NavLink href="/map" pathname={pathname} icon="🗺️" label="地图视图" />
              <NavLink href="/chargers" pathname={pathname} icon="🔌" label="监测中心" />
              <NavLink href="/charger-management" pathname={pathname} icon="➕" label="新充电桩管理" />
              <NavLink href="/messages" pathname={pathname} icon="💬" label="客服消息" />
            </div>
          </nav>
          
          {/* 主内容区 */}
          <main style={{ flex: 1 }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

function NavLink({ href, pathname, icon, label }: { href: string; pathname: string; icon: string; label: string }) {
  const isActive = pathname === href;
  return (
    <Link href={href} style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: 12,
      borderRadius: 8,
      textDecoration: "none",
      color: isActive ? "#fff" : "#aaa",
      backgroundColor: isActive ? "#007AFF" : "transparent",
      fontWeight: isActive ? "600" : "normal",
    }}>
      <span style={{ fontSize: 20 }}>{icon}</span>
      <span>{label}</span>
    </Link>
  );
}


