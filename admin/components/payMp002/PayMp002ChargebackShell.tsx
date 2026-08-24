'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { usePermissions } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import {
  getChargebackCase,
  getChargebackCases,
  PayMp002AdminError,
} from '@/lib/payMp002';
import {
  canUsePayMp002Permission,
  canonicalErrorMessageKey,
  payMp002ScopeLabel,
  resolvePayMp002Scope,
} from '@/lib/payMp002Foundation';
import type { ChargebackCaseProjection, CursorPage } from '@/lib/payMp002Types';

const CHARGEBACK_STATUSES = ['', 'received', 'under_review', 'hold', 'representment', 'won', 'lost', 'reversed', 'unknown'] as const;

function ProjectionError({ error, retry }: { error: unknown; retry: () => void }) {
  const { t } = useI18n();
  const canonical = error instanceof PayMp002AdminError ? error.canonical : null;
  return (
    <div role="alert" className="space-y-2 text-red-300">
      <p>{t(canonical ? canonicalErrorMessageKey(canonical) : 'payMp002.error')}</p>
      {canonical?.reference && <p className="font-mono text-xs text-slate-400">{canonical.reference}</p>}
      {canonical?.current_version !== undefined && (
        <p className="text-xs text-slate-400">{t('payMp002.version')}: {canonical.current_version}</p>
      )}
      <button type="button" onClick={retry} className="text-sm underline">{t('refresh')}</button>
    </div>
  );
}

function SafeTimeline({ timeline }: { timeline: unknown[] }) {
  return (
    <ul className="space-y-2 text-xs text-slate-400">
      {timeline.map((event, index) => {
        const item = event as { type?: string | null; status?: string | null; occurred_at?: string | null; reference?: string | null };
        return (
          <li key={`${item.occurred_at ?? 'event'}-${index}`} className="rounded border border-slate-700 px-3 py-2">
            <span>{item.type ?? 'event'}</span>
            <span className="ml-2">{item.status ?? 'unknown'}</span>
            {item.occurred_at && <span className="ml-2">{item.occurred_at}</span>}
            {item.reference && <span className="ml-2 font-mono">{item.reference}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function ChargebackDetail({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const { t } = useI18n();
  const detail = useSWR<ChargebackCaseProjection>(['pay-mp-002', 'chargeback-detail', caseId], () => getChargebackCase(caseId));

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm text-slate-300 underline">{t('payMp002.chargeback.back')}</button>
      {detail.isLoading && <p className="text-slate-300">{t('payMp002.loading')}</p>}
      {detail.error && <ProjectionError error={detail.error} retry={() => void detail.mutate()} />}
      {detail.data && (
        <>
          <header>
            <h1 className="text-3xl font-bold text-white">{t('payMp002.nav.chargebacks')}</h1>
            <p className="mt-1 font-mono text-sm text-slate-400">{detail.data.case_id}</p>
          </header>
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-3 text-white">
                <span>{detail.data.status}</span>
                <span className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300">{t('payMp002.version')}: {detail.data.version}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 text-sm text-slate-300 md:grid-cols-2">
              <span>{t('payMp002.chargeback.deadline')}: {detail.data.deadline_at ?? '—'}</span>
              <span>{t('payMp002.chargeback.fundsState')}: {detail.data.funds_state}</span>
              <span>{t('payMp002.chargeback.paymentReference')}: {detail.data.payment_reference}</span>
              <span>{t('payMp002.chargeback.invoiceReference')}: {detail.data.invoice_reference}</span>
              <span>{t('payMp002.chargeback.amount')}: {detail.data.amount}</span>
              <span>{t('payMp002.chargeback.currency')}: {detail.data.currency}</span>
              <span className="md:col-span-2">{t('payMp002.allowedActions')}: {detail.data.allowed_actions.join(', ') || '—'}</span>
            </CardContent>
          </Card>
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader><CardTitle className="text-white">{t('payMp002.safeTimeline')}</CardTitle></CardHeader>
            <CardContent><SafeTimeline timeline={detail.data.timeline} /></CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export function PayMp002ChargebackShell() {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const scope = useMemo(() => resolvePayMp002Scope(user, currentTenant), [currentTenant, user]);
  const canRead = canUsePayMp002Permission(permissions, 'chargeback.read');
  const [draftStatus, setDraftStatus] = useState('');
  const [draftFrom, setDraftFrom] = useState('');
  const [draftTo, setDraftTo] = useState('');
  const [status, setStatus] = useState('');
  const [deadlineFrom, setDeadlineFrom] = useState('');
  const [deadlineTo, setDeadlineTo] = useState('');
  const [cursor, setCursor] = useState<string | undefined>();
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const shouldFetch = scope.kind !== 'unavailable' && canRead && !permissionsLoading && selectedCaseId === null;
  const cacheKey = useMemo(
    () => shouldFetch ? ['pay-mp-002', `chargebacks:${scope.ref}:${status}:${deadlineFrom}:${deadlineTo}`, cursor ?? null] as const : null,
    [cursor, deadlineFrom, deadlineTo, scope.ref, shouldFetch, status],
  );
  const list = useSWR<CursorPage<ChargebackCaseProjection>>(
    cacheKey,
    () => getChargebackCases({ status: status || undefined, deadline_from: deadlineFrom || undefined, deadline_to: deadlineTo || undefined, cursor, limit: 20 }),
  );

  if (scope.kind === 'unavailable') return <p className="text-slate-300">{t('payMp002.scopeUnavailable')}</p>;
  if (!permissionsLoading && !canRead) return <p className="text-slate-300">{t('payMp002.noPermission')}</p>;
  if (selectedCaseId) return <ChargebackDetail caseId={selectedCaseId} onBack={() => setSelectedCaseId(null)} />;
  if (permissionsLoading || list.isLoading) return <p className="text-slate-300">{t('payMp002.loading')}</p>;
  if (list.error) return <ProjectionError error={list.error} retry={() => void list.mutate()} />;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white">{t('payMp002.nav.chargebacks')}</h1>
        <p className="mt-1 text-slate-400">{t('payMp002.nav.chargebacksDescription')}</p>
      </header>
      <div data-testid="pay-mp-002-scope-banner" className="rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3 text-sm text-slate-300">
        <span className="text-slate-500">{t('payMp002.scope')}: </span><span className="font-mono">{payMp002ScopeLabel(scope)}</span>
      </div>
      <form className="grid gap-3 rounded-lg border border-slate-700 bg-slate-800/60 p-4 md:grid-cols-4" onSubmit={(event) => { event.preventDefault(); setStatus(draftStatus); setDeadlineFrom(draftFrom); setDeadlineTo(draftTo); setCursor(undefined); }}>
        <label className="text-sm text-slate-300">{t('payMp002.chargeback.status')}
          <select value={draftStatus} onChange={(event) => setDraftStatus(event.target.value)} className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-2">
            {CHARGEBACK_STATUSES.map((value) => <option key={value} value={value}>{value || 'all'}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-300">{t('payMp002.chargeback.deadlineFrom')}
          <input type="datetime-local" value={draftFrom} onChange={(event) => setDraftFrom(event.target.value)} className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-2" />
        </label>
        <label className="text-sm text-slate-300">{t('payMp002.chargeback.deadlineTo')}
          <input type="datetime-local" value={draftTo} onChange={(event) => setDraftTo(event.target.value)} className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-2" />
        </label>
        <div className="flex items-end gap-2">
          <button type="submit" className="rounded bg-purple-600 px-3 py-2 text-sm text-white">{t('payMp002.chargeback.apply')}</button>
          <button type="button" onClick={() => { setDraftStatus(''); setDraftFrom(''); setDraftTo(''); setStatus(''); setDeadlineFrom(''); setDeadlineTo(''); setCursor(undefined); }} className="rounded border border-slate-600 px-3 py-2 text-sm text-slate-300">{t('payMp002.chargeback.clear')}</button>
        </div>
      </form>
      {!list.data?.items.length ? <p className="text-slate-300">{t('payMp002.empty')}</p> : (
        <div className="space-y-3">
          {list.data.items.map((item) => (
            <Card key={item.case_id} className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between gap-3 text-white">
                  <span className="font-mono text-sm">{item.case_id}</span>
                  <span className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300">{item.status}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm text-slate-400 md:grid-cols-4">
                <span>{t('payMp002.chargeback.deadline')}: {item.deadline_at ?? '—'}</span>
                <span>{t('payMp002.chargeback.fundsState')}: {item.funds_state}</span>
                <span>{t('payMp002.version')}: {item.version}</span>
                <button type="button" onClick={() => setSelectedCaseId(item.case_id)} className="text-left text-purple-300 underline">{t('payMp002.chargeback.details')}</button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {list.data?.page.has_more && list.data.page.next_cursor && <button type="button" onClick={() => setCursor(list.data?.page.next_cursor ?? undefined)} className="text-sm text-purple-300 underline">{t('payMp002.reconciliation.next')}</button>}
    </div>
  );
}
