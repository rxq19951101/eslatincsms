'use client';

import { useState } from 'react';
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

export interface RemoteStopSessionSummary {
  id: string;
  site: string;
  charger: string;
  connector: string;
}

interface RemoteStopDialogProps {
  open: boolean;
  session: RemoteStopSessionSummary | null;
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (operationReason: string) => Promise<boolean>;
}

export default function RemoteStopDialog({
  open,
  session,
  submitting,
  onOpenChange,
  onConfirm,
}: RemoteStopDialogProps) {
  const handleOpenChange = (nextOpen: boolean) => {
    if (!submitting) onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {open && (
        <RemoteStopDialogContent
          key={session?.id ?? 'no-session'}
          session={session}
          submitting={submitting}
          onOpenChange={onOpenChange}
          onConfirm={onConfirm}
        />
      )}
    </Dialog>
  );
}

function RemoteStopDialogContent({
  session,
  submitting,
  onOpenChange,
  onConfirm,
}: Omit<RemoteStopDialogProps, 'open'>) {
  const { t } = useI18n();
  const [reason, setReason] = useState('');
  const trimmedReason = reason.trim();
  const reasonIsValid = trimmedReason.length >= 3 && trimmedReason.length <= 200;

  const handleConfirm = async () => {
    if (!session || !reasonIsValid || submitting) return;
    const succeeded = await onConfirm(trimmedReason);
    if (succeeded) onOpenChange(false);
  };

  return (
    <DialogContent className="border-slate-700 bg-slate-900 text-slate-100">
        <DialogHeader>
          <DialogTitle>{t('远程停止确认')}</DialogTitle>
          <DialogDescription className="text-slate-400">
            {t('请核对会话并填写本次操作原因')}
          </DialogDescription>
        </DialogHeader>

        {session && (
          <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-2 rounded-md border border-slate-700 bg-slate-800/70 p-4 text-sm">
            <dt className="text-slate-400">{t('站点')}</dt>
            <dd className="break-words text-slate-100">{session.site}</dd>
            <dt className="text-slate-400">{t('设备')}</dt>
            <dd className="break-words text-slate-100">{session.charger}</dd>
            <dt className="text-slate-400">{t('枪口')}</dt>
            <dd className="break-words text-slate-100">{session.connector}</dd>
          </dl>
        )}

        <div className="space-y-2">
          <Label htmlFor="remote-stop-reason" className="text-slate-300">
            {t('操作原因')}
          </Label>
          <textarea
            id="remote-stop-reason"
            data-testid="remote-stop-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            disabled={submitting}
            rows={4}
            placeholder={t('请填写现场调试或故障处置原因')}
            className="w-full resize-y rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <div className="flex justify-between gap-3 text-xs">
            <span className={trimmedReason.length > 0 && !reasonIsValid ? 'text-red-400' : 'text-slate-500'}>
              {t('操作原因去除首尾空格后须为 3-200 个字符')}
            </span>
            <span className={trimmedReason.length > 200 ? 'shrink-0 text-red-400' : 'shrink-0 text-slate-500'}>
              {trimmedReason.length}/200
            </span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting} className="border-slate-600">
            {t('取消')}
          </Button>
          <Button
            data-testid="remote-stop-confirm"
            onClick={handleConfirm}
            disabled={!session || !reasonIsValid || submitting}
            className="bg-red-700 hover:bg-red-800"
          >
            {submitting ? t('停止中...') : t('确认停止')}
          </Button>
        </DialogFooter>
    </DialogContent>
  );
}
