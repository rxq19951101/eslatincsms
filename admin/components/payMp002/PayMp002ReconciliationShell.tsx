'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { usePermissions } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import {
  createReconciliationExport,
  createResolutionIntent,
  decideTemporaryAcceptance,
  getReconciliationExceptions,
  getReconciliationExport,
  getReconciliationItems,
  getReconciliationRun,
  getReconciliationRuns,
  PayMp002AdminError,
  reconciliationCsvFilename,
  requestTemporaryAcceptance,
  safeReconciliationDownloadPath,
} from '@/lib/payMp002';
import type {
  CursorPage,
  ReconciliationExceptionProjection,
  ReconciliationExportProjection,
  ReconciliationItemProjection,
  ReconciliationRunProjection,
} from '@/lib/payMp002Types';
import {
  canUsePayMp002Permission,
  canonicalErrorMessageKey,
  hasAllowedAction,
  payMp002CacheKey,
  payMp002ScopeLabel,
  projectionFrame,
  resolvePayMp002Scope,
} from '@/lib/payMp002Foundation';

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `recon-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function canonicalCode(error: unknown): string | null {
  return error instanceof PayMp002AdminError ? error.canonical.code : null;
}

function ErrorNotice({ error }: { error: unknown }) {
  const { t } = useI18n();
  const canonical = error instanceof PayMp002AdminError ? error.canonical : null;
  return (
    <div role="alert" className="space-y-1 text-sm text-red-300">
      <p>{t(canonical ? canonicalErrorMessageKey(canonical) : 'payMp002.error')}</p>
      {canonical?.reference && <p className="font-mono text-xs text-slate-500">{canonical.reference}</p>}
    </div>
  );
}

export function PayMp002ReconciliationShell() {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const scope = useMemo(() => resolvePayMp002Scope(user, currentTenant), [currentTenant, user]);
  const tenantScope = scope.kind === 'tenant' ? scope.ref : undefined;
  const canRead = canUsePayMp002Permission(permissions, 'reconciliation.read');
  const canResolve = canUsePayMp002Permission(permissions, 'reconciliation.resolve');
  const canRequestTemporary = canUsePayMp002Permission(permissions, 'reconciliation.exception.request');
  const canApproveTemporary = canUsePayMp002Permission(permissions, 'reconciliation.exception.approve');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [itemCursor, setItemCursor] = useState<string | undefined>();
  const [exceptionCursor, setExceptionCursor] = useState<string | undefined>();
  const [resolutionCode, setResolutionCode] = useState('');
  const [reason, setReason] = useState('');
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [exportId, setExportId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const enabled = scope.kind !== 'unavailable' && canRead && !permissionsLoading;

  const runPage = useSWR<CursorPage<ReconciliationRunProjection>>(
    enabled ? payMp002CacheKey('reconciliation', scope, 'runs') : null,
    () => getReconciliationRuns({ limit: 20, tenant_scope: tenantScope }),
  );
  const runDetail = useSWR<ReconciliationRunProjection>(
    enabled && selectedRunId ? ['pay-mp-002', `run-detail:${scope.ref}`, selectedRunId] : null,
    () => getReconciliationRun(selectedRunId as string, tenantScope),
  );
  const itemPage = useSWR<CursorPage<ReconciliationItemProjection>>(
    enabled && selectedRunId ? ['pay-mp-002', `items:${scope.ref}:${selectedRunId}`, itemCursor ?? null] : null,
    () => getReconciliationItems({ runId: selectedRunId as string, cursor: itemCursor, limit: 20, tenant_scope: tenantScope }),
  );
  const exceptionPage = useSWR<CursorPage<ReconciliationExceptionProjection>>(
    enabled ? ['pay-mp-002', `exceptions:${scope.ref}`, exceptionCursor ?? null] : null,
    () => getReconciliationExceptions({ cursor: exceptionCursor, limit: 20, tenant_scope: tenantScope }),
  );
  const exportPage = useSWR<ReconciliationExportProjection>(
    enabled && exportId ? ['pay-mp-002', `export:${scope.ref}`, exportId] : null,
    () => getReconciliationExport(exportId as string, tenantScope),
    { refreshInterval: (data) => data && ['queued', 'generating'].includes(data.status) ? 2000 : 0 },
  );

  if (scope.kind === 'unavailable') return <p className="text-slate-300">{t('payMp002.scopeUnavailable')}</p>;
  if (!permissionsLoading && !canRead) return <p className="text-slate-300">{t('payMp002.noPermission')}</p>;
  if (permissionsLoading || runPage.isLoading) return <p className="text-slate-300">{t('payMp002.loading')}</p>;
  if (runPage.error) return <ErrorNotice error={runPage.error} />;

  async function submitIntent(kind: 'resolve' | 'temporary' | 'decision', exception: ReconciliationExceptionProjection) {
    setBusy(true);
    try {
      if (kind === 'resolve') {
        await createResolutionIntent(exception.exception_id, {
          resolution_code: resolutionCode.trim(), reason: reason.trim(), expected_version: exception.version,
        }, idempotencyKey(), tenantScope);
      } else if (kind === 'temporary') {
        await requestTemporaryAcceptance(exception.exception_id, {
          reason: reason.trim(), expected_version: exception.version,
        }, idempotencyKey(), tenantScope);
      } else {
        await decideTemporaryAcceptance(exception.exception_id, {
          decision, reason: reason.trim(), expected_version: exception.version,
        }, idempotencyKey(), tenantScope);
      }
      setReason('');
      setResolutionCode('');
      await exceptionPage.mutate();
    } finally {
      setBusy(false);
    }
  }

  async function createExport() {
    if (!selectedRunId) return;
    setBusy(true);
    try {
      const result = await createReconciliationExport(selectedRunId, { status: [] }, idempotencyKey(), tenantScope);
      setExportId(result.export_id);
    } finally {
      setBusy(false);
    }
  }

  const selectedRun = runDetail.data;
  const exportProjection = exportPage.data;
  const downloadPath = safeReconciliationDownloadPath(exportProjection?.download_path ?? null);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white">{t('payMp002.nav.reconciliation')}</h1>
        <p className="mt-1 text-slate-400">{t('payMp002.shellOnly')}</p>
      </header>
      <div data-testid="pay-mp-002-scope-banner" className="rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3 text-sm text-slate-300">
        {t('payMp002.scope')}: <span className="font-mono">{payMp002ScopeLabel(scope)}</span>
      </div>

      <Card className="border-slate-700 bg-slate-800/80">
        <CardHeader><CardTitle className="text-white">{t('payMp002.reconciliation.run')}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {runPage.data?.items.map((run) => (
            <div key={run.run_id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-slate-700 p-3 text-sm">
              <div className="text-slate-300">
                <span className="font-mono">{run.run_id}</span> · {run.business_date} · {run.status} · v{run.version}
              </div>
              <button type="button" className="text-purple-300 underline" onClick={() => { setSelectedRunId(run.run_id); setItemCursor(undefined); setExportId(null); }}>
                {t('payMp002.reconciliation.open')}
              </button>
            </div>
          ))}
          {!runPage.data?.items.length && <p className="text-slate-400">{t('payMp002.empty')}</p>}
          {runPage.data?.page.has_more && <button type="button" className="text-sm text-purple-300 underline">{t('payMp002.reconciliation.next')}</button>}
        </CardContent>
      </Card>

      {runDetail.error && <ErrorNotice error={runDetail.error} />}
      {selectedRun && (
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader><CardTitle className="text-white">{t('payMp002.reconciliation.run')} · {selectedRun.run_id}</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-300">
            <p>status: {selectedRun.status} · version: {selectedRun.version}</p>
            <p>{t('payMp002.reconciliation.sourceWatermarks')}: {Object.entries(selectedRun.source_watermarks).map(([key, value]) => `${key}=${String(value)}`).join(', ') || '—'}</p>
            <p>{t('payMp002.reconciliation.summary')}: {Object.entries(selectedRun.summary).map(([key, value]) => `${key}=${String(value)}`).join(', ') || '—'}</p>
            <div className="flex flex-wrap gap-3">
              <button type="button" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-purple-300 disabled:opacity-50" onClick={() => void createExport()}>
                {t('payMp002.reconciliation.export')}
              </button>
              {exportProjection && (
                <span data-testid="reconciliation-export-state" className="rounded border border-slate-600 px-3 py-2">
                  {t('payMp002.reconciliation.exportStatus')}: {exportProjection.status}
                </span>
              )}
            </div>
            {exportPage.error && <ErrorNotice error={exportPage.error} />}
            {exportProjection && (
              <div className="space-y-1 rounded border border-slate-700 p-3 text-xs text-slate-400">
                <p>{t('payMp002.reconciliation.auditReference')}: <span className="font-mono">{exportProjection.audit_reference}</span></p>
                <p>{t('payMp002.reconciliation.contentType')}</p>
                {downloadPath && exportProjection.status === 'ready' && (
                  <a
                    href={downloadPath}
                    download={reconciliationCsvFilename(exportProjection.export_id)}
                    className="text-purple-300 underline"
                    onClick={() => window.setTimeout(() => void exportPage.mutate(), 250)}
                  >
                    {t('payMp002.reconciliation.download')}
                  </a>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {selectedRunId && (
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader><CardTitle className="text-white">{t('payMp002.reconciliation.items')}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {itemPage.error && <ErrorNotice error={itemPage.error} />}
            {itemPage.data?.items.map((item) => (
              <div key={item.item_id} className="rounded border border-slate-700 p-3 text-sm text-slate-300">
                <p className="font-mono">{item.item_id}</p>
                <p>{item.match_status} · {item.currency} {item.amount ?? '—'} · {item.reason_codes.join(', ') || '—'}</p>
                <p className="text-xs text-slate-500">v{item.version} · {item.eslatin_reference ?? '—'} / {item.provider_reference ?? '—'} / {item.funds_reference ?? '—'}</p>
              </div>
            ))}
            {itemPage.data?.page.has_more && <button type="button" className="text-sm text-purple-300 underline" onClick={() => setItemCursor(itemPage.data?.page.next_cursor ?? undefined)}>{t('payMp002.reconciliation.next')}</button>}
          </CardContent>
        </Card>
      )}

      <Card className="border-slate-700 bg-slate-800/80">
        <CardHeader><CardTitle className="text-white">{t('payMp002.reconciliation.exceptions')}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {exceptionPage.error && <ErrorNotice error={exceptionPage.error} />}
          {exceptionPage.data?.items.map((exception) => {
            const frame = projectionFrame(exception, scope);
            return (
              <div key={exception.exception_id} className="space-y-3 rounded border border-slate-700 p-3 text-sm text-slate-300">
                <p className="font-mono">{exception.exception_id}</p>
                <p>{exception.status} · {exception.category} · {exception.currency} {exception.difference_amount ?? '—'} · v{exception.version}</p>
                <p className="text-xs text-slate-500">owner: {exception.owner ?? '—'} · due: {exception.due_at ?? '—'} · actions: {frame.allowed_actions.join(', ') || '—'}</p>
                <div className="grid gap-2 md:grid-cols-2">
                  {canResolve && hasAllowedAction(exception, 'resolve') && (
                    <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void submitIntent('resolve', exception); }}>
                      <input value={resolutionCode} onChange={(event) => setResolutionCode(event.target.value)} required placeholder={t('payMp002.reconciliation.resolutionCode')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                      <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.reconciliation.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                      <button type="submit" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-purple-300 disabled:opacity-50">{t('payMp002.reconciliation.submitIntent')}</button>
                    </form>
                  )}
                  {canRequestTemporary && hasAllowedAction(exception, 'request_temporary_acceptance') && (
                    <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void submitIntent('temporary', exception); }}>
                      <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.reconciliation.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                      <button type="submit" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-purple-300 disabled:opacity-50">{t('payMp002.reconciliation.requestTemporary')}</button>
                    </form>
                  )}
                  {canApproveTemporary && (
                    <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void submitIntent('decision', exception); }}>
                      <select value={decision} onChange={(event) => setDecision(event.target.value as 'approve' | 'reject')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white">
                        <option value="approve">{t('payMp002.reconciliation.approve')}</option>
                        <option value="reject">{t('payMp002.reconciliation.reject')}</option>
                      </select>
                      <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.reconciliation.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                      <button type="submit" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-purple-300 disabled:opacity-50">{t('payMp002.reconciliation.decideTemporary')}</button>
                    </form>
                  )}
                </div>
              </div>
            );
          })}
          {exceptionPage.data?.page.has_more && <button type="button" className="text-sm text-purple-300 underline" onClick={() => setExceptionCursor(exceptionPage.data?.page.next_cursor ?? undefined)}>{t('payMp002.reconciliation.next')}</button>}
        </CardContent>
      </Card>
    </div>
  );
}
