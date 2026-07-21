import type { DashboardSummary } from '@/types';
import type { Locale, MessageKey } from '@/lib/i18n';

const localeTags: Record<Locale, string> = {
  'zh-CN': 'zh-CN',
  en: 'en-US',
  es: 'es-CO',
};

const statusKeys: Record<string, MessageKey> = {
  active: 'status.ongoing',
  ongoing: 'status.ongoing',
  completed: 'status.completed',
  cancelled: 'status.cancelled',
  canceled: 'status.cancelled',
  failed: 'status.failed',
};

export interface DashboardChargePointMetrics {
  total: number;
  online: number;
  offline: number;
  charging: number;
  available: number;
  faulted: number;
}

function finiteNumber(value: number | string | null | undefined): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function normalizeDashboardChargePointMetrics(
  summary?: DashboardSummary,
): DashboardChargePointMetrics {
  return {
    total: finiteNumber(summary?.total_charge_points),
    online: finiteNumber(summary?.online_charge_points),
    offline: finiteNumber(summary?.offline_charge_points),
    charging: finiteNumber(summary?.charging_charge_points),
    available: finiteNumber(summary?.available_charge_points),
    faulted: finiteNumber(summary?.faulted_charge_points),
  };
}

export function getStatusMessageKey(status: string | null | undefined): MessageKey {
  const normalized = status?.trim().toLowerCase();
  return (normalized && statusKeys[normalized]) || 'status.unknown';
}

export function getStatusBadgeClass(status: string | null | undefined): string {
  switch (status?.trim().toLowerCase()) {
    case 'active':
    case 'ongoing':
      return 'bg-blue-500/20 text-blue-400';
    case 'completed':
      return 'bg-green-500/20 text-green-400';
    case 'cancelled':
    case 'canceled':
    case 'failed':
      return 'bg-red-500/20 text-red-400';
    default:
      return 'bg-slate-500/20 text-slate-300';
  }
}

export function isOngoingStatus(status: string | null | undefined): boolean {
  const normalized = status?.trim().toLowerCase();
  return normalized === 'ongoing' || normalized === 'active';
}

export function formatDateTime(
  value: string | null | undefined,
  locale: Locale,
  fallback: string,
): string {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(localeTags[locale], {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date);
}

export function formatDate(
  value: string | number | null | undefined,
  locale: Locale,
  fallback: string,
): string {
  if (value === null || value === undefined || value === '') return fallback;
  const source = String(value);
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(source) ? `${source}T00:00:00Z` : source);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(localeTags[locale], {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(date);
}

export function formatMeasurement(
  value: number | null | undefined,
  fractionDigits: number,
  unit: string,
  fallback: string,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;
  return `${value.toFixed(fractionDigits)}${unit ? ` ${unit}` : ''}`;
}
