import type { SiteStatusCounts } from '../api/sites';
import { COLORS } from '../constants/config';

export type SiteStatusCountKey = keyof SiteStatusCounts;

export interface SiteStatusBreakdownItem {
  status: SiteStatusCountKey;
  count: number;
}

export type SiteAvailability =
  | 'availableToCharge'
  | 'siteNoConnectorsFree'
  | 'temporarilyUnavailable';

const STATUS_ORDER: SiteStatusCountKey[] = [
  'available',
  'charging',
  'occupied',
  'offline',
  'faulted',
  'unavailable',
  'unknown',
];

const STATUS_COLORS: Record<SiteStatusCountKey, string> = {
  available: COLORS.SUCCESS,
  charging: COLORS.WARNING,
  occupied: COLORS.WARNING,
  offline: COLORS.TEXT_SECONDARY,
  faulted: COLORS.ERROR,
  unavailable: COLORS.TEXT_SECONDARY,
  unknown: COLORS.TEXT_SECONDARY,
};

export const getSiteStatusBreakdown = (
  counts?: SiteStatusCounts,
): SiteStatusBreakdownItem[] => {
  if (!counts) return [];

  return STATUS_ORDER.flatMap((status) => {
    const count = counts[status];
    return Number.isFinite(count) && count > 0 ? [{ status, count }] : [];
  });
};

export const hasChargingWithoutAvailability = (
  availableConnectors: number,
  counts?: SiteStatusCounts,
): boolean => availableConnectors <= 0 && (counts?.charging ?? 0) > 0;

export const getSiteAvailability = (
  availableConnectors: number | null | undefined,
  counts?: SiteStatusCounts,
  legacyStatus?: string | null,
): SiteAvailability => {
  if ((availableConnectors ?? 0) > 0 || (counts?.available ?? 0) > 0) {
    return 'availableToCharge';
  }

  if (counts) {
    if (counts.charging > 0 || counts.occupied > 0) {
      return 'siteNoConnectorsFree';
    }
    return 'temporarilyUnavailable';
  }

  switch (legacyStatus?.toLowerCase()) {
    case 'available':
      return 'availableToCharge';
    case 'charging':
    case 'occupied':
      return 'siteNoConnectorsFree';
    case 'offline':
    case 'unavailable':
    case 'faulted':
    default:
      return 'temporarilyUnavailable';
  }
};

export const getSiteStatusColor = (status: SiteStatusCountKey): string =>
  STATUS_COLORS[status];
