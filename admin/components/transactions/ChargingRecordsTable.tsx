'use client';

import { AlertTriangle, FileText } from 'lucide-react';

import { useI18n } from '@/lib/i18n';
import {
  formatDateTime,
  getStatusBadgeClass,
  getStatusMessageKey,
  isOngoingStatus,
} from '@/lib/localization';
import type { ChargingRecord, TransactionAnomalyCode } from '@/types';

interface ChargingRecordsTableProps {
  records: ChargingRecord[];
  compact?: boolean;
  showSite?: boolean;
}

const anomalyKeys: Record<TransactionAnomalyCode, string> = {
  invalid_meter_delta: 'transactions.anomaly.invalidMeterDelta',
  missing_end_time: 'transactions.anomaly.missingEndTime',
  power_exceeds_rating: 'transactions.anomaly.powerExceedsRating',
};

const paymentKeys: Record<string, string> = {
  created: 'transactions.payment.created',
  pending: 'transactions.payment.pending',
  processing: 'transactions.payment.processing',
  approved: 'transactions.payment.paid',
  paid: 'transactions.payment.paid',
  unpaid: 'transactions.payment.unpaid',
  issued: 'transactions.payment.issued',
  declined: 'transactions.payment.declined',
  rejected: 'transactions.payment.declined',
  voided: 'transactions.payment.voided',
  error: 'transactions.payment.failed',
  failed: 'transactions.payment.failed',
  expired: 'transactions.payment.expired',
  refunded: 'transactions.payment.refunded',
  cancelled: 'transactions.payment.cancelled',
  canceled: 'transactions.payment.cancelled',
};

function finiteNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDecimal(
  value: number | string | null | undefined,
  locale: string,
  fractionDigits: number,
  fallback: string,
): string {
  const parsed = finiteNumber(value);
  if (parsed === null) return fallback;
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(parsed);
}

function formatAmount(record: ChargingRecord, locale: string, notSettled: string, fallback: string): string {
  const amount = finiteNumber(record.amount);
  if (amount === null) return notSettled;
  const currency = typeof record.currency === 'string' ? record.currency.trim().toUpperCase() : '';
  if (!/^[A-Z]{3}$/.test(currency)) {
    return formatDecimal(amount, locale, 2, fallback);
  }
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      currencyDisplay: 'code',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${formatDecimal(amount, locale, 2, fallback)}`;
  }
}

function normalizedPaymentKey(status: string | null | undefined): string {
  if (typeof status !== 'string') return 'transactions.payment.unavailable';
  const normalized = status.trim().toLowerCase();
  return paymentKeys[normalized] || 'transactions.payment.unknown';
}

function primaryReference(record: ChargingRecord, fallback: string): string {
  const invoice = typeof record.invoice_number === 'string' ? record.invoice_number.trim() : '';
  const chargingRecord = typeof record.record_number === 'string' ? record.record_number.trim() : '';
  return invoice || chargingRecord || fallback;
}

export default function ChargingRecordsTable({
  records,
  compact = false,
  showSite = true,
}: ChargingRecordsTableProps) {
  const { locale, t } = useI18n();
  const fallback = t('common.notAvailable');

  if (records.length === 0) {
    return (
      <div className="py-12 text-center">
        <FileText className="mx-auto mb-4 h-12 w-12 text-slate-500" />
        <p className="text-slate-400">{t('transactions.empty')}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[920px]">
        <thead>
          <tr className="border-b border-slate-700">
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.record')}</th>
            {!compact && showSite && (
              <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.location')}</th>
            )}
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.user')}</th>
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.period')}</th>
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.energyDuration')}</th>
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.amountPayment')}</th>
            <th className="px-3 py-3 text-left text-sm font-medium text-slate-400">{t('transactions.state')}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => {
            const anomalies = Array.isArray(record.anomaly_codes) ? record.anomaly_codes : [];
            const displayCode = record.charger?.display_code?.trim() || record.charger?.ocpp_identity?.trim() || fallback;
            const displayName = record.charger?.display_name?.trim();
            const connectorReference = record.connector?.physical_reference?.trim();
            const connectorDetails = [
              connectorReference,
              record.connector?.connector_type?.trim(),
              finiteNumber(record.connector?.max_power_kw) === null
                ? null
                : `${formatDecimal(record.connector?.max_power_kw, locale, 2, fallback)} kW`,
            ].filter(Boolean).join(' · ');
            return (
              <tr
                key={record.id}
                data-testid="admin-transaction-row"
                className="border-b border-slate-700/50 align-top hover:bg-slate-700/30"
              >
                <td className="px-3 py-4">
                  <p className="font-medium text-white">{primaryReference(record, fallback)}</p>
                  {record.invoice_number && record.record_number && (
                    <p className="mt-1 text-xs text-slate-400">{record.record_number}</p>
                  )}
                  {compact && (
                    <p className="mt-1 text-xs text-slate-400">
                      {connectorDetails || fallback}
                    </p>
                  )}
                </td>
                {!compact && showSite && (
                  <td className="px-3 py-4 text-sm">
                    <p className="text-slate-200">{record.site?.name?.trim() || fallback}</p>
                    <p className="mt-1 text-slate-400">
                      {[displayCode, displayName, connectorDetails].filter(Boolean).join(' · ') || fallback}
                    </p>
                  </td>
                )}
                <td className="px-3 py-4 text-sm text-slate-300">
                  {record.user_reference?.trim() || fallback}
                </td>
                <td className="px-3 py-4 text-sm text-slate-300">
                  <p>{formatDateTime(record.start_time, locale, fallback)}</p>
                  <p className="mt-1 text-slate-400">
                    {record.end_time
                      ? formatDateTime(record.end_time, locale, fallback)
                      : isOngoingStatus(record.status)
                        ? t('status.ongoing')
                        : fallback}
                  </p>
                </td>
                <td className="px-3 py-4 text-sm text-slate-300">
                  <p>{formatDecimal(record.energy_kwh, locale, 3, fallback)} kWh</p>
                  <p className="mt-1 text-slate-400">
                    {formatDecimal(record.duration_minutes, locale, 2, fallback)} {t('transactions.minutes')}
                  </p>
                </td>
                <td className="px-3 py-4 text-sm">
                  <p className={record.amount === null || record.amount === undefined ? 'text-amber-300' : 'text-slate-200'}>
                    {formatAmount(record, locale, t('transactions.notSettled'), fallback)}
                  </p>
                  <p className="mt-1 text-slate-400">{t(normalizedPaymentKey(record.payment_status))}</p>
                </td>
                <td className="px-3 py-4 text-sm">
                  <span className={`inline-flex rounded-md px-2 py-1 text-xs ${getStatusBadgeClass(record.status)}`}>
                    {t(getStatusMessageKey(record.status))}
                  </span>
                  {anomalies.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {anomalies.map((code) => (
                        <div key={code} className="flex items-start gap-1.5 text-xs text-amber-300">
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{t(anomalyKeys[code] || 'transactions.anomaly.unknown')}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
