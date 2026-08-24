'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { usePermissions } from '@/hooks/usePermissions';
import { useI18n } from '@/lib/i18n';
import {
  closeRuntimeRail,
  decideRuntimeRailReopen,
  getRuntimeRails,
  PayMp002AdminError,
  requestRuntimeRailReopen,
} from '@/lib/payMp002';
import type {
  CursorPage,
  RailReopenRequestProjection,
  RuntimeRailControlProjection,
} from '@/lib/payMp002Types';
import {
  canUsePayMp002Permission,
  canonicalErrorMessageKey,
  hasAllowedAction,
  payMp002CacheKey,
  payMp002ScopeLabel,
  resolvePayMp002Scope,
} from '@/lib/payMp002Foundation';

function idempotencyKey(prefix: string): string {
  return globalThis.crypto?.randomUUID?.() ?? `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function actorLabel(actor: RuntimeRailControlProjection['closed_by']): string {
  return actor ? `${actor.display_name} (${actor.role_label})` : '—';
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

export function PayMp002RailShell() {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const scope = useMemo(() => resolvePayMp002Scope(user, currentTenant), [currentTenant, user]);
  const canRead = canUsePayMp002Permission(permissions, 'rail.read');
  const canClose = canUsePayMp002Permission(permissions, 'rail.close');
  const canRequestReopen = canUsePayMp002Permission(permissions, 'rail.reopen.request');
  const canApproveReopen = canUsePayMp002Permission(permissions, 'rail.reopen.approve');
  const enabled = scope.kind !== 'unavailable' && canRead && !permissionsLoading;
  const page = useSWR<CursorPage<RuntimeRailControlProjection>>(
    enabled ? payMp002CacheKey('rails', scope, 'controls') : null,
    () => getRuntimeRails({
      scope_type: scope.kind === 'tenant' ? 'tenant' : 'platform',
      scope_id: scope.ref ?? undefined,
      limit: 50,
    }),
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reopenRequest, setReopenRequest] = useState<RailReopenRequestProjection | null>(null);
  const [reason, setReason] = useState('');
  const [incidentReference, setIncidentReference] = useState('');
  const [healthCheckReference, setHealthCheckReference] = useState('');
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');

  if (scope.kind === 'unavailable') return <p className="text-slate-300">{t('payMp002.scopeUnavailable')}</p>;
  if (!permissionsLoading && !canRead) return <p className="text-slate-300">{t('payMp002.noPermission')}</p>;
  if (permissionsLoading || page.isLoading) return <p className="text-slate-300">{t('payMp002.loading')}</p>;
  if (page.error) return <ErrorNotice error={page.error} />;

  async function closeRail(rail: RuntimeRailControlProjection) {
    setBusy(true);
    setActionError(null);
    try {
      await closeRuntimeRail({
        axis: rail.axis,
        scope: rail.scope,
        reason: reason.trim(),
        incident_reference: incidentReference.trim(),
        expected_version: rail.version,
      }, idempotencyKey('rail-close'));
      setReason('');
      setIncidentReference('');
      await page.mutate();
    } catch (error) {
      setActionError(error);
    } finally {
      setBusy(false);
    }
  }

  async function requestReopen(rail: RuntimeRailControlProjection) {
    setBusy(true);
    setActionError(null);
    try {
      const result = await requestRuntimeRailReopen(rail.control_id, {
        reason: reason.trim(),
        health_check_reference: healthCheckReference.trim(),
        expected_version: rail.version,
      }, idempotencyKey('rail-reopen-request'));
      setReopenRequest(result);
      setReason('');
      setHealthCheckReference('');
    } catch (error) {
      setActionError(error);
    } finally {
      setBusy(false);
    }
  }

  async function decideReopen(request: RailReopenRequestProjection) {
    setBusy(true);
    setActionError(null);
    try {
      const result = await decideRuntimeRailReopen(request.request_id, {
        decision,
        reason: reason.trim(),
        expected_version: request.version,
      }, idempotencyKey('rail-reopen-decision'));
      setReopenRequest(result);
      setReason('');
      await page.mutate();
    } catch (error) {
      setActionError(error);
    } finally {
      setBusy(false);
    }
  }

  const rails = page.data?.items ?? [];
  const renderRail = (rail: RuntimeRailControlProjection) => {
    const unsafeState = rail.status === 'unknown';
    const canCloseThis = canClose && rail.status === 'open' && hasAllowedAction(rail, 'close');
    const canRequestThis = canRequestReopen && hasAllowedAction(rail, 'request_reopen');
    const requestForRail = reopenRequest?.control_id === rail.control_id ? reopenRequest : null;
    const canDecideRequest = requestForRail && canApproveReopen
      && hasAllowedAction(requestForRail, decision);
    return (
      <Card key={rail.control_id} className="border-slate-700 bg-slate-800/80">
        <CardHeader className="pb-3">
          <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-white">
            <span>{rail.axis}</span>
            <span className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-300">{rail.status}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-300">
          <div className="grid gap-2 md:grid-cols-2">
            <span>{t('payMp002.rail.control')}: <span className="font-mono">{rail.control_id}</span></span>
            <span>{t('payMp002.scope')}: <span className="font-mono">{rail.scope.ref}</span></span>
            <span>{t('payMp002.rail.version')}: {rail.version}</span>
            <span>{t('payMp002.rail.effectiveAt')}: {rail.effective_at ?? '—'}</span>
            <span>{t('payMp002.rail.reason')}: {rail.reason ?? '—'}</span>
            <span>{t('payMp002.rail.incident')}: {rail.incident_reference ?? '—'}</span>
            <span>{t('payMp002.rail.closedBy')}: {actorLabel(rail.closed_by)}</span>
            <span>{t('payMp002.rail.reopenedBy')}: {actorLabel(rail.reopened_by)}</span>
            <span>{t('payMp002.rail.health')}: {rail.health_check_reference ?? '—'}</span>
            <span>{t('payMp002.allowedActions')}: {rail.allowed_actions.join(', ') || '—'}</span>
          </div>
          {unsafeState && <p className="rounded border border-amber-700/70 bg-amber-950/30 p-2 text-amber-200">{t('payMp002.rail.unknownSafe')}</p>}

          {(canCloseThis || canRequestThis) && (
            <div className="grid gap-3 border-t border-slate-700 pt-3 md:grid-cols-2">
              {canCloseThis && (
                <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void closeRail(rail); }}>
                  <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.rail.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                  <input value={incidentReference} onChange={(event) => setIncidentReference(event.target.value)} required placeholder={t('payMp002.rail.incident')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                  <button type="submit" disabled={busy} className="rounded border border-red-700 px-3 py-2 text-red-200 disabled:opacity-50">{t('payMp002.rail.close')}</button>
                </form>
              )}
              {canRequestThis && (
                <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void requestReopen(rail); }}>
                  <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.rail.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                  <input value={healthCheckReference} onChange={(event) => setHealthCheckReference(event.target.value)} required placeholder={t('payMp002.rail.healthReference')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                  <button type="submit" disabled={busy} className="rounded border border-slate-600 px-3 py-2 text-purple-200 disabled:opacity-50">{t('payMp002.rail.requestReopen')}</button>
                </form>
              )}
            </div>
          )}

          {requestForRail && (
            <div className="space-y-2 rounded border border-slate-700 p-3 text-xs text-slate-400">
              <p>{t('payMp002.rail.reopenRequest')}: <span className="font-mono">{requestForRail.request_id}</span> · {requestForRail.status} · {t('payMp002.rail.controlStatus')}: {requestForRail.control_status}</p>
              <p>{t('payMp002.rail.initiator')}: {actorLabel(requestForRail.initiator)} · {t('payMp002.rail.approver')}: {actorLabel(requestForRail.approver)}</p>
              <p>{t('payMp002.rail.healthReference')}: {requestForRail.health_check_reference} · {t('payMp002.rail.expiresAt')}: {requestForRail.expires_at}</p>
              {canApproveReopen && (hasAllowedAction(requestForRail, 'approve') || hasAllowedAction(requestForRail, 'reject')) && (
                <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void decideReopen(requestForRail); }}>
                  <select value={decision} onChange={(event) => setDecision(event.target.value as 'approve' | 'reject')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white">
                    <option value="approve">{t('payMp002.rail.approve')}</option>
                    <option value="reject">{t('payMp002.rail.reject')}</option>
                  </select>
                  <input value={reason} onChange={(event) => setReason(event.target.value)} required placeholder={t('payMp002.rail.reason')} className="w-full rounded border border-slate-600 bg-slate-900 p-2 text-white" />
                  <button type="submit" disabled={busy || !canDecideRequest} className="rounded border border-slate-600 px-3 py-2 text-purple-200 disabled:opacity-50">{t('payMp002.rail.submitDecision')}</button>
                </form>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white">{t('payMp002.nav.rails')}</h1>
        <p className="mt-1 text-slate-400">{t('payMp002.rail.description')}</p>
      </header>
      <div data-testid="pay-mp-002-scope-banner" className="rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3 text-sm text-slate-300">
        {t('payMp002.scope')}: <span className="font-mono">{payMp002ScopeLabel(scope)}</span>
      </div>
      <p className="rounded border border-slate-700 bg-slate-800/50 p-3 text-sm text-slate-400">{t('payMp002.rail.closeBoundary')}</p>
      {actionError !== null && <ErrorNotice error={actionError} />}
      {(['paid_admission', 'payment_creation'] as const).map((axis) => (
        <section key={axis} className="space-y-3" aria-labelledby={`rail-axis-${axis}`}>
          <h2 id={`rail-axis-${axis}`} className="text-xl font-semibold text-white">{axis}</h2>
          {rails.filter((rail) => rail.axis === axis).map(renderRail)}
          {!rails.some((rail) => rail.axis === axis) && <p className="text-sm text-slate-400">{t('payMp002.empty')}</p>}
        </section>
      ))}
      {page.data?.page.has_more && <p className="text-xs text-slate-500">{t('payMp002.rail.nextPage')}</p>}
    </div>
  );
}
