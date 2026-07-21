import { describe, expect, it } from 'vitest';

import { createMoneyFormatter, normalizeCurrency } from '@/lib/money';

describe('admin money formatting', () => {
  it('formats the tenant currency for a Spanish locale without a yuan symbol', () => {
    const formatted = createMoneyFormatter('es', 'cop')(3750.75);

    expect(formatted).toContain('3750,75');
    expect(formatted).toContain('COP');
    expect(formatted).not.toContain('¥');
  });

  it('falls back to the current COP business default for an invalid config value', () => {
    expect(normalizeCurrency(undefined)).toBe('COP');
    expect(normalizeCurrency('invalid')).toBe('COP');
  });
});
