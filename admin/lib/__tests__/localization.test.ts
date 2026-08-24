import { describe, expect, it } from 'vitest';
import { translateMessage, type Locale } from '@/lib/i18n';
import {
  formatDate,
  formatDateTime,
  formatMeasurement,
  getStatusMessageKey,
  normalizeDashboardChargePointMetrics,
} from '@/lib/localization';
import type { DashboardSummary } from '@/types';

describe('admin localization helpers', () => {
  it.each([
    ['zh-CN', '进行中', '已完成', '已取消', '未提供'],
    ['en', 'In progress', 'Completed', 'Cancelled', 'Not available'],
    ['es', 'En curso', 'Completada', 'Cancelada', 'No disponible'],
  ] as const)('localizes session states and missing values for %s', (locale, ongoing, completed, cancelled, missing) => {
    expect(translateMessage(locale, getStatusMessageKey('ongoing'))).toBe(ongoing);
    expect(translateMessage(locale, getStatusMessageKey('Completed'))).toBe(completed);
    expect(translateMessage(locale, getStatusMessageKey('cancelled'))).toBe(cancelled);
    expect(translateMessage(locale, 'common.notAvailable')).toBe(missing);
  });

  it.each([
    ['zh-CN', 'zh-CN'],
    ['en', 'en-US'],
    ['es', 'es-CO'],
  ] as const)('formats date and time with the %s locale', (locale, localeTag) => {
    const value = '2026-07-18T15:30:45Z';
    const expected = new Intl.DateTimeFormat(localeTag, {
      dateStyle: 'medium',
      timeStyle: 'medium',
    }).format(new Date(value));

    expect(formatDateTime(value, locale as Locale, 'missing')).toBe(expected);
    expect(formatDate('2026-07-18', locale as Locale, 'missing')).not.toBe('missing');
  });

  it('preserves zero measurements and localizes invalid defaults at the call site', () => {
    expect(formatMeasurement(0, 2, 'kWh', 'Not available')).toBe('0.00 kWh');
    expect(formatMeasurement(undefined, 2, 'kWh', 'Not available')).toBe('Not available');
    expect(formatDateTime('invalid', 'en', 'Not available')).toBe('Not available');
  });

  it('uses every unified dashboard metric exactly as returned by the API', () => {
    const summary = {
      total_charge_points: 10,
      online_charge_points: 8,
      offline_charge_points: 7,
      charging_charge_points: 3,
      available_charge_points: 4,
      faulted_charge_points: 1,
    } as DashboardSummary;

    expect(normalizeDashboardChargePointMetrics(summary)).toEqual({
      total: 10,
      online: 8,
      offline: 7,
      charging: 3,
      available: 4,
      faulted: 1,
    });
  });
});
