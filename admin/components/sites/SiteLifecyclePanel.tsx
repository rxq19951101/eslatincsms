'use client';

import { useState } from 'react';
import { Archive, ExternalLink, RotateCcw, Trash2 } from 'lucide-react';

import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';
import { formatDateTime } from '@/lib/localization';
import type { SiteDetail } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export interface SiteArchiveBlocker {
  type: string;
  resource_id: string;
  resource_type?: string;
  display_code?: string | null;
}

interface SiteArchivePreflight {
  site_id: string;
  lifecycle_status: 'active' | 'archived';
  can_archive_now: boolean;
  counts: {
    active_charge_points: number;
    retiring_charge_points: number;
    retired_charge_points: number;
    ongoing_sessions: number;
    unsettled_business_records: number;
  };
  blockers: SiteArchiveBlocker[];
}

interface SiteLifecyclePanelProps {
  site: SiteDetail;
  canWrite: boolean;
  onChanged: () => Promise<unknown> | unknown;
  onDeleted: () => void;
  onOpenBlocker: (blocker: SiteArchiveBlocker) => void;
}

type Action = 'archive' | 'restore' | 'delete';

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export default function SiteLifecyclePanel({
  site,
  canWrite,
  onChanged,
  onDeleted,
  onOpenBlocker,
}: SiteLifecyclePanelProps) {
  const { locale, t } = useI18n();
  const isArchived = site.lifecycle_status === 'archived';
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [preflight, setPreflight] = useState<SiteArchivePreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const normalizedReason = reason.trim();
  const reasonValid = normalizedReason.length >= 3 && normalizedReason.length <= 500;
  const confirmationValid = confirmation === site.site_code;
  const canConfirm = reasonValid
    && !submitting
    && (action !== 'archive' || Boolean(preflight?.can_archive_now))
    && (action !== 'delete' || confirmationValid);

  const resetDialog = () => {
    setAction(null);
    setReason('');
    setConfirmation('');
    setPreflight(null);
    setPreflightLoading(false);
    setFeedback(null);
  };

  const openAction = async (nextAction: Action) => {
    setAction(nextAction);
    setReason('');
    setConfirmation('');
    setPreflight(null);
    setFeedback(null);
    if (nextAction !== 'archive') return;

    setPreflightLoading(true);
    try {
      const result = await apiGet<SiteArchivePreflight>(API_ENDPOINTS.SITE_ARCHIVE_PREFLIGHT(site.id));
      setPreflight(result);
    } catch (error) {
      setFeedback(errorMessage(error, t('归档预检失败，请稍后重试')));
    } finally {
      setPreflightLoading(false);
    }
  };

  const submit = async () => {
    if (!action || !canConfirm) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      if (action === 'archive') {
        await apiPost(API_ENDPOINTS.SITE_ARCHIVE(site.id), { reason: normalizedReason });
        await onChanged();
        resetDialog();
        return;
      }
      if (action === 'restore') {
        await apiPost(API_ENDPOINTS.SITE_RESTORE(site.id), { reason: normalizedReason });
        await onChanged();
        resetDialog();
        return;
      }

      await apiDelete(API_ENDPOINTS.SITE_DETAIL(site.id), {
        confirmation,
        reason: normalizedReason,
      });
      resetDialog();
      onDeleted();
    } catch (error) {
      setFeedback(errorMessage(error, t('操作失败，请检查阻塞项后重试')));
    } finally {
      setSubmitting(false);
    }
  };

  const dialogTitle = action === 'archive'
    ? t('归档站点')
    : action === 'restore'
      ? t('恢复站点')
      : t('永久删除站点');

  const counts = preflight?.counts;

  return (
    <>
      <Card data-testid="site-lifecycle-panel" className="border-slate-700 bg-slate-800/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-white">{t('资产生命周期')}</CardTitle>
            <Badge className={isArchived
              ? 'border-amber-500/50 bg-amber-500/20 text-amber-300'
              : 'border-green-500/50 bg-green-500/20 text-green-300'}>
              {isArchived ? t('已归档') : t('运营中')}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 text-sm md:grid-cols-3">
            <div>
              <p className="text-slate-400">{t('正常充电桩')}</p>
              <p className="mt-1 text-lg font-semibold text-slate-100">{site.active_charge_points_count ?? site.charge_points.length}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('已退役充电桩')}</p>
              <p className="mt-1 text-lg font-semibold text-slate-100">{site.retired_charge_points_count ?? 0}</p>
            </div>
            <div>
              <p className="text-slate-400">{t('归档时间')}</p>
              <p className="mt-1 text-slate-100">
                {formatDateTime(site.archived_at, locale, t('common.notAvailable'))}
              </p>
            </div>
          </div>

          {isArchived && (
            <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              <p><span className="font-semibold">{t('归档原因')}：</span>{site.archive_reason || t('common.notAvailable')}</p>
              <p>{t('归档站点不会出现在正常运营列表；恢复站点不会自动恢复其退役充电桩。')}</p>
            </div>
          )}

          {canWrite && (
            <div className="flex flex-wrap gap-3">
              {isArchived ? (
                <Button data-testid="admin-site-restore" type="button" onClick={() => void openAction('restore')}>
                  <RotateCcw className="h-4 w-4" />
                  {t('恢复站点')}
                </Button>
              ) : (
                <Button data-testid="admin-site-archive" type="button" variant="outline" onClick={() => void openAction('archive')}>
                  <Archive className="h-4 w-4" />
                  {t('归档站点')}
                </Button>
              )}
              <Button data-testid="admin-site-delete" type="button" variant="destructive" onClick={() => void openAction('delete')}>
                <Trash2 className="h-4 w-4" />
                {t('永久删除')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={action !== null} onOpenChange={(open) => {
        if (!open && !submitting) resetDialog();
      }}>
        <DialogContent data-testid="site-lifecycle-dialog" className="border-slate-700 bg-slate-900 text-slate-100 sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {action === 'archive'
                ? t('归档前必须先迁移或退役正常充电桩，并处理所有进行中会话和未结业务。')
                : action === 'restore'
                  ? t('恢复后站点重新进入运营列表，但站点下的退役充电桩仍保持退役。')
                  : t('仅完全未使用的站点可永久删除，此操作不可恢复。')}
            </DialogDescription>
          </DialogHeader>

          {action === 'archive' && (
            <div className="space-y-3">
              {preflightLoading && <p className="text-sm text-slate-400">{t('正在检查充电桩、会话和账务状态...')}</p>}
              {counts && (
                <>
                  <div className="grid grid-cols-2 gap-2 text-center text-sm md:grid-cols-5">
                    {[
                      [counts.active_charge_points, t('正常充电桩')],
                      [counts.retiring_charge_points, t('退役中充电桩')],
                      [counts.retired_charge_points, t('已退役充电桩')],
                      [counts.ongoing_sessions, t('进行中会话')],
                      [counts.unsettled_business_records, t('未结业务')],
                    ].map(([value, label]) => (
                      <div key={String(label)} className="rounded-md bg-slate-800 p-3">
                        <p className="text-xl font-semibold">{value}</p>
                        <p className="text-slate-400">{label}</p>
                      </div>
                    ))}
                  </div>
                  {counts.retired_charge_points > 0 && (
                    <p className="text-sm text-slate-400">{t('退役充电桩不阻止归档，但会保留在资产归档中并阻止永久删除。')}</p>
                  )}
                </>
              )}

              {preflight && !preflight.can_archive_now && (
                <div data-testid="site-archive-blockers" role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
                  <p className="font-semibold">{t('当前不能归档，请先处理以下阻塞项：')}</p>
                  <ul className="mt-2 space-y-2">
                    {preflight.blockers.map((blocker) => (
                      <li key={`${blocker.type}-${blocker.resource_id}`} className="flex items-center justify-between gap-3 rounded bg-red-950/30 px-3 py-2">
                        <span className="min-w-0 break-all">
                          {t(blocker.type)} · {blocker.display_code || blocker.resource_id}
                        </span>
                        <Button
                          data-testid={`site-blocker-open-${blocker.resource_id}`}
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => onOpenBlocker(blocker)}
                          className="shrink-0 border-red-400/40 bg-transparent text-red-100 hover:bg-red-500/20"
                        >
                          <ExternalLink className="h-3 w-3" />
                          {t('处理')}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="site-lifecycle-reason" className="text-sm font-medium text-slate-200">{t('操作原因')}</label>
            <textarea
              id="site-lifecycle-reason"
              data-testid="site-lifecycle-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={submitting}
              maxLength={500}
              rows={3}
              className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              placeholder={t('请填写 3-500 个字符')}
            />
          </div>

          {action === 'delete' && (
            <div className="space-y-2">
              <label htmlFor="site-delete-confirmation" className="text-sm font-medium text-slate-200">
                {t('输入站点编号以确认永久删除')}
              </label>
              <code className="block break-all rounded bg-slate-800 px-3 py-2 text-sm text-amber-200">{site.site_code}</code>
              <input
                id="site-delete-confirmation"
                data-testid="site-delete-confirmation"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                disabled={submitting}
                autoComplete="off"
                className="h-10 w-full rounded-md border border-slate-600 bg-slate-800 px-3 text-sm text-white outline-none focus:border-red-500"
              />
            </div>
          )}

          {feedback && <p role="alert" className="text-sm text-red-300">{feedback}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={submitting} onClick={resetDialog}>{t('取消')}</Button>
            <Button
              data-testid="site-lifecycle-confirm"
              type="button"
              variant={action === 'delete' ? 'destructive' : 'default'}
              disabled={!canConfirm}
              onClick={() => void submit()}
            >
              {submitting ? t('处理中...') : t('确认操作')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
