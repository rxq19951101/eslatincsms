'use client';

import type { PricingDetails } from '@/types';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/lib/i18n';
import { formatDateTime } from '@/lib/localization';
import { createMoneyFormatter } from '@/lib/money';

const modeLabels = {
  paid: '付费',
  free: '免费',
  unavailable: '暂不可用',
  inherit: '继承站点',
} as const;

const sourceLabels = {
  charger: '充电桩覆盖',
  site: '站点默认',
  none: '无',
} as const;

export default function PricingSummary({ pricing }: { pricing?: PricingDetails | null }) {
  const { locale, t } = useI18n();
  const effective = pricing ?? {
    pricing_mode: 'unavailable' as const,
    pricing_source: 'none' as const,
    currency: 'COP',
  };
  const price = effective.base_price_per_kwh == null ? null : Number(effective.base_price_per_kwh);
  const formatMoney = createMoneyFormatter(locale, effective.currency || 'COP');

  return (
    <div className="grid grid-cols-1 gap-3 rounded-md border border-slate-700 bg-slate-900/40 p-4 text-sm md:grid-cols-2" data-testid="pricing-summary">
      <div>
        <div className="text-slate-400">{t('定价模式')}</div>
        <Badge className="mt-1 border-slate-600 bg-slate-700/60 text-slate-100">
          {t(modeLabels[effective.pricing_mode])}
        </Badge>
      </div>
      <div>
        <div className="text-slate-400">{t('价格来源')}</div>
        <div className="mt-1 text-slate-100">{t(sourceLabels[effective.pricing_source])}</div>
      </div>
      {effective.pricing_mode === 'paid' && price != null && Number.isFinite(price) && (
        <div>
          <div className="text-slate-400">{t('有效价格')}</div>
          <div className="mt-1 text-slate-100">{formatMoney(price)} / kWh</div>
        </div>
      )}
      {effective.pricing_mode === 'free' && (
        <>
          <div>
            <div className="text-slate-400">{t('有效价格')}</div>
            <div className="mt-1 text-emerald-300">{t('免费')} · {formatMoney(0)} / kWh</div>
          </div>
          <div>
            <div className="text-slate-400">{t('免费原因')}</div>
            <div className="mt-1 text-slate-100">{effective.free_reason || t('common.notAvailable')}</div>
          </div>
          <div>
            <div className="text-slate-400">{t('免费截止时间')}</div>
            <div className="mt-1 text-slate-100">
              {formatDateTime(effective.valid_until, locale, t('common.notAvailable'))}
            </div>
          </div>
        </>
      )}
      {effective.pricing_mode === 'unavailable' && (
        <div className="md:col-span-2 text-amber-300">{t('未配置商业定价，禁止新充电会话。')}</div>
      )}
    </div>
  );
}
