'use client';

import { useRequireAuth } from '@/hooks/useAuth';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { useI18n } from '@/lib/i18n';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isReady } = useRequireAuth();
  const { t } = useI18n();

  // 登录页面不需要布局（已经在 (auth) 路由组中处理，不会进入此布局）

  // 如果正在加载或认证校验未完成/未认证，显示加载状态
  if (!isReady || !isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950">
        <div className="text-slate-400">{t('加载中...')}</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-950 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6 bg-slate-900/50">
          {children}
        </main>
      </div>
    </div>
  );
}
