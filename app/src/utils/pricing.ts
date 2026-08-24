import type { AppLocale, I18nKeys } from '../i18n';

export type PricingMode = 'paid' | 'free' | 'unavailable';

export interface PricingInfo {
  pricing_mode: PricingMode;
  pricing_source: 'charger' | 'site' | 'none';
  tariff_id: string | null;
  base_price_per_kwh: string | null;
  service_fee: string | null;
  currency: string;
  free_reason: string | null;
  valid_from: string | null;
  valid_until: string | null;
}

const localeTags: Record<AppLocale, string> = { es: 'es-CO', en: 'en-US', zh: 'zh-CN' };

/** Missing pricing is never interpreted as zero or free. */
export function formatPricing(
  pricing: PricingInfo | null | undefined,
  t: I18nKeys,
  locale: AppLocale
): string | null {
  if (!pricing || pricing.pricing_mode === 'unavailable') return null;
  if (pricing.pricing_mode === 'free') return `${t.pricing.free} · 0 COP/kWh`;
  const amount = Number(pricing.base_price_per_kwh);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return `${amount.toLocaleString(localeTags[locale], { maximumFractionDigits: 2 })} ${pricing.currency || 'COP'}/kWh`;
}

export function pricingNumericValue(pricing: PricingInfo | null | undefined): number | null {
  if (!pricing || pricing.pricing_mode !== 'paid') return null;
  const amount = Number(pricing.base_price_per_kwh);
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}
