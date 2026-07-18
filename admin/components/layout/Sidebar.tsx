'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Zap,
  FileText,
  BarChart3,
  Bell,
  Users,
  Building2,
  Map,
  Settings,
  Menu,
  X,
  CreditCard,
  Activity,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/authStore';
import { usePermissions, hasPermission } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import Image from 'next/image';

const navigation = [
  { key: 'dashboard', href: '/', icon: LayoutDashboard },
  { key: 'sites', href: '/sites', icon: Zap, permission: 'sites.read' },
  { key: 'transactions', href: '/transactions', icon: FileText, permission: 'transactions.read' },
  { key: 'sessions', href: '/sessions', icon: Activity, permission: 'transactions.read' },
  { key: 'payments', href: '/payments', icon: CreditCard, superAdminOnly: true },
  { key: 'reports', href: '/statistics', icon: BarChart3, permission: 'reports.read' },
  { key: 'alerts', href: '/alerts', icon: Bell, permission: 'alerts.read' },
  { key: 'users', href: '/users', icon: Users, permission: 'admin_users.read' },
  { key: 'tenants', href: '/tenants', icon: Building2, superAdminOnly: true },
  { key: 'map', href: '/map', icon: Map, permission: 'sites.read' },
  { key: 'settings', href: '/settings', icon: Settings, permission: 'configs.read' },
];

export function Sidebar() {
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const { permissions, isLoading } = usePermissions();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { t } = useI18n();
  const visibleNavigation = navigation.filter((item) => {
    if (item.superAdminOnly) return !!user?.is_super_admin;
    if (!item.permission || user?.is_super_admin || isLoading) return true;
    return hasPermission(permissions, item.permission);
  });

  return (
    <>
      {/* Mobile menu button */}
      <div className="lg:hidden fixed top-4 left-4 z-50">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="bg-slate-800/80 backdrop-blur-sm border-slate-700 text-slate-300 hover:bg-slate-700"
        >
          {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed lg:static inset-y-0 left-0 z-40 w-64 bg-slate-900/95 backdrop-blur-sm border-r border-slate-800 transform transition-transform duration-300 ease-in-out',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Brand */}
          <div className="flex items-center gap-2 px-6 py-6 border-b border-slate-800">
            <Image src="/brand/eslatin-symbol-dark.svg" alt="" aria-hidden="true" width={48} height={48} className="h-12 w-12 object-contain" />
            <div>
              <h1 className="text-xl font-bold text-white">EsLatin</h1>
              <p className="text-xs text-slate-400">{t('adminPortal')}</p>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
            {visibleNavigation.map((item) => {
              const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-gradient-to-r from-purple-600/20 to-blue-600/20 text-purple-400 border-l-2 border-purple-500'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {t(item.key as Parameters<typeof t>[0])}
                </Link>
              );
            })}
          </nav>

          {/* User section (移动端显示) */}
          <div className="lg:hidden p-4 border-t border-slate-800">
            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-800/50">
              <div className="h-10 w-10 rounded-full bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center text-white font-semibold">
                A
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{user?.username || t('管理员')}</p>
                <p className="text-xs text-slate-400 truncate">{user?.email || ''}</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Overlay (移动端) */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}
    </>
  );
}
