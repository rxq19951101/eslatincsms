import type { Locale } from '@/lib/i18n';

export const DEFAULT_CURRENCY = 'COP';

export function normalizeCurrency(value: unknown): string {
  if (typeof value !== 'string') return DEFAULT_CURRENCY;
  const currency = value.trim().toUpperCase();
  return /^[A-Z]{3}$/.test(currency) ? currency : DEFAULT_CURRENCY;
}

export function createMoneyFormatter(locale: Locale, currency: string): (amount: number) => string {
  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: normalizeCurrency(currency),
    currencyDisplay: 'code',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (amount: number) => formatter.format(amount);
}
