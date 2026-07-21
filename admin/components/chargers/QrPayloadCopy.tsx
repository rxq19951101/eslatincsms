'use client';

import { useState } from 'react';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useI18n } from '@/lib/i18n';

interface QrPayloadCopyProps {
  qrToken?: string | null;
  connectorId: number;
}

export function publicScanPayload(qrToken: string): string {
  return `qr:${qrToken}`;
}

export default function QrPayloadCopy({ qrToken, connectorId }: QrPayloadCopyProps) {
  const { t } = useI18n();
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');

  if (!qrToken) return null;
  const payload = publicScanPayload(qrToken);

  const copyPayload = async () => {
    try {
      await navigator.clipboard.writeText(payload);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
  };

  return (
    <div className="space-y-2" data-testid={`admin-qr-payload-region-${connectorId}`}>
      <Input
        readOnly
        value={payload}
        aria-label={t('扫码载荷')}
        data-testid={`admin-qr-payload-${connectorId}`}
        className="bg-slate-800 border-slate-600 text-slate-200 font-mono text-xs"
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={copyPayload}
        data-testid={`admin-qr-copy-payload-${connectorId}`}
        className="w-full bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
      >
        <Copy className="h-4 w-4 mr-2" />
        {copyState === 'copied'
          ? t('已复制')
          : copyState === 'failed'
            ? t('复制失败')
            : t('复制扫码载荷')}
      </Button>
    </div>
  );
}
