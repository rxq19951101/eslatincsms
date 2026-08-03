'use client';

import { useState } from 'react';
import { AlertTriangle, Archive, RotateCcw, Trash2 } from 'lucide-react';

import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';
import { formatDateTime } from '@/lib/localization';
import { ChargePointDetail } from '@/types';
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

interface RetirementBlocker {
  type: string;
  resource_id: string;
}

interface RetirementPreflight {
  charge_point_id: string;
  lifecycle_status: 'active' | 'retired';
  can_retire_now: boolean;
  will_wait_for_sessions: boolean;
  counts: {
    ongoing_sessions: number;
    pending_remote_commands: number;
    unsettled_business_records: number;
  };
  blockers: RetirementBlocker[];
}

interface RestoreResponse {
  lifecycle_status: 'active';
  commissioning_status: 'testing';
  ocpp_identity: string;
  ocpp_secret: string | null;
  credential_rotated: boolean;
}

interface ChargerLifecyclePanelProps {
  charger: ChargePointDetail;
  canWrite: boolean;
  onChanged: () => Promise<unknown> | unknown;
  onDeleted: () => void;
}

type Action = 'retire' | 'restore' | 'delete';

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export default function ChargerLifecyclePanel({
  charger,
  canWrite,
  onChanged,
  onDeleted,
}: ChargerLifecyclePanelProps) {
  const { locale, t } = useI18n();
  const isRetired = charger.lifecycle_status === 'retired';
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [preflight, setPreflight] = useState<RetirementPreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [restoredSecret, setRestoredSecret] = useState<string | null>(null);

  const normalizedReason = reason.trim();
  const reasonValid = normalizedReason.length >= 3 && normalizedReason.length <= 500;
  const deleteConfirmationValid = confirmation === charger.ocpp_identity;
  const canConfirm = reasonValid
    && !submitting
    && (action !== 'retire' || Boolean(preflight?.can_retire_now))
    && (action !== 'delete' || deleteConfirmationValid);

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
    setFeedback(null);
    setPreflight(null);
    if (nextAction !== 'retire') return;

    setPreflightLoading(true);
    try {
      const result = await apiGet<RetirementPreflight>(
        API_ENDPOINTS.CHARGER_RETIREMENT_PREFLIGHT(charger.id)
      );
      setPreflight(result);
    } catch (error) {
      setFeedback(errorMessage(error, t('退役预检失败，请稍后重试')));
    } finally {
      setPreflightLoading(false);
    }
  };

  const submit = async () => {
    if (!action || !canConfirm) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      if (action === 'retire') {
        await apiPost(API_ENDPOINTS.CHARGER_RETIRE(charger.id), { reason: normalizedReason });
        await onChanged();
        resetDialog();
        return;
      }
      if (action === 'restore') {
        const result = await apiPost<RestoreResponse>(API_ENDPOINTS.CHARGER_RESTORE(charger.id), {
          reason: normalizedReason,
        });
        if (result.credential_rotated && result.ocpp_secret) {
          setRestoredSecret(result.ocpp_secret);
        }
        await onChanged();
        resetDialog();
        return;
      }

      await apiDelete(API_ENDPOINTS.CHARGER_DETAIL(charger.id), {
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

  const dialogTitle = action === 'retire'
    ? t('退役充电桩')
    : action === 'restore'
      ? t('恢复充电桩')
      : t('永久删除充电桩');

  return (
    <>
      <Card data-testid="charger-lifecycle-panel" className="border-slate-700 bg-slate-800/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-white">{t('资产生命周期')}</CardTitle>
            <Badge className={isRetired
              ? 'border-amber-500/50 bg-amber-500/20 text-amber-300'
              : 'border-green-500/50 bg-green-500/20 text-green-300'}>
              {isRetired ? t('已退役') : t('运营中')}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isRetired && (
            <div className="grid gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-slate-400">{t('退役时间')}</p>
                <p className="mt-1 text-slate-100">
                  {formatDateTime(charger.retired_at, locale, t('common.notAvailable'))}
                </p>
              </div>
              <div>
                <p className="text-slate-400">{t('退役原因')}</p>
                <p className="mt-1 text-slate-100">{charger.retirement_reason || t('common.notAvailable')}</p>
              </div>
              <div>
                <p className="text-slate-400">{t('原所属站点')}</p>
                <p className="mt-1 text-slate-100">
                  {charger.original_site?.name || charger.original_site?.site_code || t('common.notAvailable')}
                </p>
              </div>
            </div>
          )}

          {isRetired && (
            <div className="flex gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{t('退役充电桩不会出现在站点运营视图，二维码和远程控制均已停用。')}</p>
            </div>
          )}

          {restoredSecret && (
            <div data-testid="charger-restored-secret" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-amber-100">
              <p className="font-semibold">{t('恢复后的新密钥只显示这一次')}</p>
              <code className="mt-2 block break-all">{restoredSecret}</code>
            </div>
          )}

          {canWrite && (
            <div className="flex flex-wrap gap-3">
              {isRetired ? (
                <Button data-testid="admin-charger-restore" type="button" onClick={() => void openAction('restore')}>
                  <RotateCcw className="h-4 w-4" />
                  {t('恢复充电桩')}
                </Button>
              ) : (
                <Button data-testid="admin-charger-retire" type="button" variant="outline" onClick={() => void openAction('retire')}>
                  <Archive className="h-4 w-4" />
                  {t('退役充电桩')}
                </Button>
              )}
              <Button data-testid="admin-charger-delete" type="button" variant="destructive" onClick={() => void openAction('delete')}>
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
        <DialogContent data-testid="charger-lifecycle-dialog" className="border-slate-700 bg-slate-900 text-slate-100 sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {action === 'retire'
                ? t('预检通过并填写原因后，充电桩将从运营站点中隐藏且无法连接。')
                : action === 'restore'
                  ? t('恢复后设备进入测试状态，并生成只显示一次的新 OCPP 密钥。')
                  : t('仅误创建且完全未使用的草稿充电桩可永久删除，此操作不可恢复。')}
            </DialogDescription>
          </DialogHeader>

          {action === 'retire' && (
            <div className="space-y-3">
              {preflightLoading && <p className="text-sm text-slate-400">{t('正在检查会话、指令和账务状态...')}</p>}
              {preflight && (
                <>
                  <div className="grid grid-cols-3 gap-2 text-center text-sm">
                    <div className="rounded-md bg-slate-800 p-3">
                      <p className="text-xl font-semibold">{preflight.counts.ongoing_sessions}</p>
                      <p className="text-slate-400">{t('进行中会话')}</p>
                    </div>
                    <div className="rounded-md bg-slate-800 p-3">
                      <p className="text-xl font-semibold">{preflight.counts.pending_remote_commands}</p>
                      <p className="text-slate-400">{t('待执行指令')}</p>
                    </div>
                    <div className="rounded-md bg-slate-800 p-3">
                      <p className="text-xl font-semibold">{preflight.counts.unsettled_business_records}</p>
                      <p className="text-slate-400">{t('未结业务')}</p>
                    </div>
                  </div>
                  {!preflight.can_retire_now && (
                    <div data-testid="charger-retirement-blockers" role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
                      <p className="font-semibold">{t('当前不能退役，请先处理以下阻塞项：')}</p>
                      <ul className="mt-2 list-disc space-y-1 pl-5">
                        {preflight.blockers.map((blocker) => (
                          <li key={`${blocker.type}-${blocker.resource_id}`}>
                            {t(blocker.type)} · {blocker.resource_id}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="charger-lifecycle-reason" className="text-sm font-medium text-slate-200">
              {t('操作原因')}
            </label>
            <textarea
              id="charger-lifecycle-reason"
              data-testid="charger-lifecycle-reason"
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
              <label htmlFor="charger-delete-confirmation" className="text-sm font-medium text-slate-200">
                {t('输入 OCPP 技术身份以确认永久删除')}
              </label>
              <code className="block break-all rounded bg-slate-800 px-3 py-2 text-sm text-amber-200">
                {charger.ocpp_identity}
              </code>
              <input
                id="charger-delete-confirmation"
                data-testid="charger-delete-confirmation"
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
            <Button type="button" variant="outline" disabled={submitting} onClick={resetDialog}>
              {t('取消')}
            </Button>
            <Button
              data-testid="charger-lifecycle-confirm"
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
