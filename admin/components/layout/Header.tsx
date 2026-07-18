'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { UserMenu } from './UserMenu';
import { Bell, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS, REFRESH_INTERVAL } from '@/lib/constants';
import { useTenantStore } from '@/store/tenantStore';
import { useI18n } from '@/lib/i18n';
import { LanguageSwitcher } from './LanguageSwitcher';

interface AlertItem {
  id: string;
  status: string;
}

export function Header() {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { t } = useI18n();
  const { data: alerts } = useSWR<AlertItem[]>(
    `${API_ENDPOINTS.ALERTS}?status=pending&limit=50`,
    (url: string) => apiGet<AlertItem[]>(url),
    { refreshInterval: REFRESH_INTERVAL }
  );

  const pendingCount = alerts?.length ?? 0;

  return (
    <header className="h-16 bg-slate-900/80 backdrop-blur-sm border-b border-slate-800 flex items-center justify-between px-6">
      <div className="hidden md:flex flex-1 max-w-md">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            type="text"
            placeholder={t('search')}
            className="pl-10 bg-slate-800/50 border-slate-700 text-slate-200 placeholder:text-slate-500 focus:border-purple-500 w-full"
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <span className="hidden sm:inline-flex rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300">
          {currentTenant ? `${t('tenant')}: ${currentTenant.name}` : t('allPlatform')}
        </span>
        <Link href="/alerts">
          <Button
            variant="ghost"
            size="icon"
            className="relative text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          >
            <Bell className="h-5 w-5" />
            {pendingCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 rounded-full text-[10px] text-white flex items-center justify-center">
                {pendingCount > 99 ? '99+' : pendingCount}
              </span>
            )}
          </Button>
        </Link>
        <UserMenu />
        <LanguageSwitcher />
      </div>
    </header>
  );
}
