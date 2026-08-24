'use client';

import { useMemo } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { usePermissions } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import {
  getAuditEvents,
  getChargebackCases,
  getReconciliationRuns,
  getRefundCases,
  getRuntimeRails,
  getSupportCases,
  PayMp002AdminError,
} from '@/lib/payMp002';
import {
  PAY_MP_002_MEDIA_TYPE,
  type AuditEventProjection,
  type ChargebackCaseProjection,
  type CursorPage,
  type ReconciliationRunProjection,
  type RefundCaseProjection,
  type RuntimeRailControlProjection,
  type SupportCaseProjection,
} from '@/lib/payMp002Types';
import {
  PAY_MP_002_NAVIGATION,
  canUsePayMp002Permission,
  canonicalErrorMessageKey,
  payMp002CacheKey,
  payMp002ScopeLabel,
  projectionFrame,
  resolvePayMp002Scope,
  type PayMp002Resource,
} from '@/lib/payMp002Foundation';

type ResourceItem =
  | RefundCaseProjection
  | ChargebackCaseProjection
  | ReconciliationRunProjection
  | SupportCaseProjection
  | RuntimeRailControlProjection
  | AuditEventProjection;

function getResourcePage(resource: PayMp002Resource, scope: ReturnType<typeof resolvePayMp002Scope>): Promise<CursorPage<ResourceItem>> {
  const tenantScope = scope.kind === 'tenant' ? scope.ref : undefined;
  switch (resource) {
    case 'refunds':
      return getRefundCases({ tenant_scope: tenantScope, limit: 20 }) as Promise<CursorPage<ResourceItem>>;
    case 'chargebacks':
      return getChargebackCases({ limit: 20 }) as Promise<CursorPage<ResourceItem>>;
    case 'reconciliation':
      return getReconciliationRuns({ limit: 20 }) as Promise<CursorPage<ResourceItem>>;
    case 'support':
      return getSupportCases({ tenant_scope: tenantScope, limit: 20 }) as Promise<CursorPage<ResourceItem>>;
    case 'rails':
      return getRuntimeRails({ scope_type: scope.kind === 'tenant' ? 'tenant' : undefined, scope_id: scope.kind === 'tenant' ? scope.tenantId : undefined, limit: 20 }) as Promise<CursorPage<ResourceItem>>;
    case 'audit':
      return getAuditEvents({ limit: 20 }) as Promise<CursorPage<ResourceItem>>;
  }
}

function itemId(item: ResourceItem): string {
  if ('case_id' in item) return item.case_id;
  if ('run_id' in item) return item.run_id;
  if ('control_id' in item) return item.control_id;
  return item.event_id;
}

function itemStatus(item: ResourceItem): string {
  if ('status' in item) return item.status;
  return item.result;
}

function itemVersion(item: ResourceItem): number | undefined {
  return 'version' in item ? item.version : undefined;
}

function itemTimelineCount(item: ResourceItem): number {
  return 'timeline' in item ? item.timeline.length : 0;
}

export function PayMp002ResourceShell({ resource }: { resource: PayMp002Resource }) {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const scope = useMemo(() => resolvePayMp002Scope(user, currentTenant), [currentTenant, user]);
  const navigation = PAY_MP_002_NAVIGATION.find((item) => item.resource === resource);
  const canRead = !!navigation && canUsePayMp002Permission(permissions, navigation.permission);
  const shouldFetch = scope.kind !== 'unavailable' && canRead && !permissionsLoading;
  const cacheKey = payMp002CacheKey(resource, scope);
  const { data, error, isLoading, mutate } = useSWR<CursorPage<ResourceItem>>(
    shouldFetch ? cacheKey : null,
    () => getResourcePage(resource, scope),
  );

  if (!navigation) return <p className="text-slate-300">{t('payMp002.resourceNotFound')}</p>;
  if (scope.kind === 'unavailable') return <p className="text-slate-300">{t('payMp002.scopeUnavailable')}</p>;
  if (!permissionsLoading && !canRead) return <p className="text-slate-300">{t('payMp002.noPermission')}</p>;
  if (permissionsLoading || isLoading) return <p className="text-slate-300">{t('payMp002.loading')}</p>;
  if (error) {
    const canonical = error instanceof PayMp002AdminError ? error.canonical : null;
    return (
      <div role="alert" className="space-y-2 text-red-300">
        <p>{t(canonical ? canonicalErrorMessageKey(canonical) : 'payMp002.error')}</p>
        {canonical?.reference && <p className="font-mono text-xs text-slate-400">{canonical.reference}</p>}
        <button type="button" onClick={() => void mutate()} className="text-sm underline">{t('refresh')}</button>
      </div>
    );
  }

  const items = data?.items ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white">{t(navigation.labelKey)}</h1>
        <p className="mt-1 text-slate-400">{t('payMp002.shellOnly')}</p>
      </header>
      <div data-testid="pay-mp-002-scope-banner" className="rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3 text-sm text-slate-300">
        <span className="text-slate-500">{t('payMp002.scope')}: </span>
        <span className="font-mono">{payMp002ScopeLabel(scope)}</span>
        <span className="ml-4 text-slate-500">Accept: </span>
        <span className="font-mono text-xs">{PAY_MP_002_MEDIA_TYPE}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-slate-300">{t('payMp002.empty')}</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const frame = projectionFrame(item, scope);
            return (
              <Card key={itemId(item)} className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between gap-3 text-white">
                    <span className="font-mono text-sm">{itemId(item)}</span>
                    <span className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300">{itemStatus(item)}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 text-sm text-slate-400 md:grid-cols-4">
                  <span>{t('payMp002.scope')}: {payMp002ScopeLabel(frame.scope)}</span>
                  <span>{t('payMp002.version')}: {itemVersion(item) ?? '—'}</span>
                  <span>{t('payMp002.safeTimeline')}: {itemTimelineCount(item)}</span>
                  <span>{t('payMp002.allowedActions')}: {frame.allowed_actions.length ? frame.allowed_actions.join(', ') : '—'}</span>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {data?.page.has_more && <p className="text-xs text-slate-500">Next cursor available; later task owns pagination UX.</p>}
    </div>
  );
}
