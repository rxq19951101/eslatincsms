'use client';

import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useI18n } from '@/lib/i18n';

export type MaintenanceCommand = 'soft-reset' | 'hard-reset' | 'unlock';

interface EvseOption {
  id: number;
  label: string;
  status: string;
}

interface MaintenanceCommandDialogProps {
  open: boolean;
  command: MaintenanceCommand | null;
  evses: EvseOption[];
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (
    command: MaintenanceCommand,
    operationReason: string,
    connectorId?: number
  ) => Promise<boolean>;
}

export default function MaintenanceCommandDialog({
  open,
  command,
  evses,
  submitting,
  onOpenChange,
  onConfirm,
}: MaintenanceCommandDialogProps) {
  const handleOpenChange = (nextOpen: boolean) => {
    if (!submitting) onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {open && (
        <MaintenanceCommandDialogContent
          key={command ?? 'no-command'}
          command={command}
          evses={evses}
          submitting={submitting}
          onOpenChange={onOpenChange}
          onConfirm={onConfirm}
        />
      )}
    </Dialog>
  );
}

function MaintenanceCommandDialogContent({
  command,
  evses,
  submitting,
  onOpenChange,
  onConfirm,
}: Omit<MaintenanceCommandDialogProps, 'open'>) {
  const { t } = useI18n();
  const [reason, setReason] = useState('');
  const [selectedEvseId, setSelectedEvseId] = useState<number | null>(null);
  const [riskAccepted, setRiskAccepted] = useState(false);
  const trimmedReason = reason.trim();
  const reasonIsValid = trimmedReason.length >= 3 && trimmedReason.length <= 200;
  const selectionIsValid = command !== 'unlock' || selectedEvseId !== null;
  const riskIsValid = command !== 'hard-reset' || riskAccepted;

  const handleConfirm = async () => {
    if (!command || !reasonIsValid || !selectionIsValid || !riskIsValid || submitting) return;
    const succeeded = await onConfirm(command, trimmedReason, selectedEvseId ?? undefined);
    if (succeeded) onOpenChange(false);
  };

  const title = command === 'unlock'
    ? t('解锁连接器')
    : command === 'hard-reset'
      ? t('Hard Reset 危险确认')
      : t('Soft Reset');

  return (
    <DialogContent className="border-slate-700 bg-slate-900 text-slate-100">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="text-slate-400">
            {command === 'unlock'
              ? t('请选择当前充电桩的明确枪口并填写操作原因')
              : t('请填写本次维护操作的原因')}
          </DialogDescription>
        </DialogHeader>

        {command === 'hard-reset' && (
          <div className="rounded-md border border-red-500/50 bg-red-500/10 p-4 text-sm text-red-100">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
              <div>
                <p className="font-semibold">{t('Hard Reset 会中断设备当前服务')}</p>
                <p className="mt-1 text-red-200/80">
                  {t('设备将重启，进行中的充电和现场通信可能中断，请仅在故障处置时使用。')}
                </p>
              </div>
            </div>
          </div>
        )}

        {command === 'unlock' && (
          <fieldset className="space-y-2" disabled={submitting}>
            <legend className="text-sm font-medium text-slate-300">{t('选择当前充电桩枪口')}</legend>
            {evses.length > 0 ? (
              <div className="space-y-2">
                {evses.map((evse) => (
                  <label
                    key={evse.id}
                    className="flex cursor-pointer items-center justify-between gap-3 rounded-md border border-slate-700 bg-slate-800/70 p-3 hover:border-cyan-500/70"
                  >
                    <span className="flex items-center gap-3">
                      <input
                        type="radio"
                        name="maintenance-unlock-evse"
                        value={evse.id}
                        checked={selectedEvseId === evse.id}
                        onChange={() => setSelectedEvseId(evse.id)}
                        className="h-4 w-4 accent-cyan-600"
                        data-testid={`admin-unlock-evse-${evse.id}`}
                      />
                      <span className="text-slate-100">{evse.label}</span>
                    </span>
                    <span className="text-sm text-slate-400">{t(evse.status)}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="rounded-md border border-slate-700 p-3 text-sm text-slate-400">
                {t('暂无connector信息')}
              </p>
            )}
          </fieldset>
        )}

        <div className="space-y-2">
          <Label htmlFor="maintenance-command-reason" className="text-slate-300">
            {t('操作原因')}
          </Label>
          <textarea
            id="maintenance-command-reason"
            data-testid="admin-maintenance-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            disabled={submitting}
            maxLength={200}
            rows={4}
            placeholder={t('请填写现场调试或故障处置原因')}
            className="w-full resize-y rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <div className="flex justify-between gap-3 text-xs">
            <span className={trimmedReason.length > 0 && !reasonIsValid ? 'text-red-400' : 'text-slate-500'}>
              {t('操作原因去除首尾空格后须为 3-200 个字符')}
            </span>
            <span className="shrink-0 text-slate-500">{trimmedReason.length}/200</span>
          </div>
        </div>

        {command === 'hard-reset' && (
          <label className="flex cursor-pointer items-start gap-3 rounded-md border border-red-500/40 p-3 text-sm text-red-100">
            <input
              type="checkbox"
              checked={riskAccepted}
              onChange={(event) => setRiskAccepted(event.target.checked)}
              disabled={submitting}
              className="mt-0.5 h-4 w-4 accent-red-600"
              data-testid="admin-hard-reset-risk-confirm"
            />
            <span>{t('我已了解 Hard Reset 可能中断充电，并确认继续')}</span>
          </label>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting} className="border-slate-600">
            {t('取消')}
          </Button>
          <Button
            data-testid="admin-maintenance-confirm"
            onClick={handleConfirm}
            disabled={!command || !reasonIsValid || !selectionIsValid || !riskIsValid || submitting}
            className={command === 'hard-reset' ? 'bg-red-700 hover:bg-red-800' : 'bg-cyan-700 hover:bg-cyan-800'}
          >
            {submitting ? t('提交中...') : t('确认提交')}
          </Button>
        </DialogFooter>
    </DialogContent>
  );
}
