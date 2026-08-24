import { en } from '../../i18n/en';
import { es } from '../../i18n/es';
import { zh } from '../../i18n/zh';
import { formatPricing, pricingNumericValue, type PricingInfo } from '../pricing';

const paid: PricingInfo = {
  pricing_mode: 'paid',
  pricing_source: 'site',
  tariff_id: 'tariff-1',
  base_price_per_kwh: '2700.00',
  service_fee: '0.00',
  currency: 'COP',
  free_reason: null,
  valid_from: '2026-08-05T12:00:00Z',
  valid_until: null,
};

describe('explicit App pricing', () => {
  it('renders paid pricing in COP', () => {
    expect(formatPricing(paid, es, 'es')).toBe('2.700 COP/kWh');
  });

  it.each([
    [es, 'es' as const, 'Gratis · 0 COP/kWh'],
    [en, 'en' as const, 'Free · 0 COP/kWh'],
    [zh, 'zh' as const, '免费 · 0 COP/kWh'],
  ])('renders free pricing explicitly', (t, locale, expected) => {
    expect(formatPricing({ ...paid, pricing_mode: 'free', base_price_per_kwh: '0.00' }, t, locale)).toBe(expected);
  });

  it('does not turn missing pricing into zero', () => {
    expect(formatPricing(undefined, es, 'es')).toBeNull();
    expect(pricingNumericValue(undefined)).toBeNull();
    expect(pricingNumericValue({ ...paid, pricing_mode: 'free', base_price_per_kwh: '0.00' })).toBeNull();
  });
});
