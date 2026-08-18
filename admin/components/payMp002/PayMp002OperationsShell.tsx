'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { usePermissions } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import {
  PAY_MP_002_NAVIGATION,
  canUsePayMp002Permission,
  payMp002ScopeLabel,
  resolvePayMp002Scope,
} from '@/lib/payMp002Foundation';

export function PayMp002OperationsShell() {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const scope = useMemo(() => resolvePayMp002Scope(user, currentTenant), [currentTenant, user]);
  const visibleItems = PAY_MP_002_NAVIGATION.filter((item) =>
    permissionsLoading || canUsePayMp002Permission(permissions, item.permission)
  );

  if (scope.kind === 'unavailable') {
    return <p className="text-slate-300">{t('payMp002.scopeUnavailable')}</p>;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white">{t('payMp002.title')}</h1>
        <p className="mt-1 text-slate-400">{t('payMp002.foundationDescription')}</p>
      </header>

      <div data-testid="pay-mp-002-scope-banner" className="rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3 text-sm text-slate-300">
        <span className="text-slate-500">{t('payMp002.scope')}: </span>
        <span className="font-mono">{payMp002ScopeLabel(scope)}</span>
      </div>

      <p className="text-sm text-slate-400">{t('payMp002.shellOnly')}</p>

      {visibleItems.length === 0 && !permissionsLoading ? (
        <p className="text-slate-300">{t('payMp002.noPermission')}</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleItems.map((item) => (
            <Link key={item.resource} href={item.href} className="block">
              <Card className="h-full border-slate-700 bg-slate-800/80 transition-colors hover:border-purple-500/60">
                <CardHeader>
                  <CardTitle className="text-white">{t(item.labelKey)}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-slate-400">
                  {t(item.descriptionKey)}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
