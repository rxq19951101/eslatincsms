import { describe, expect, it } from 'vitest';
import { matchesSearchQuery } from '@/lib/search';

describe('matchesSearchQuery', () => {
  it('handles nullable API fields without throwing', () => {
    expect(matchesSearchQuery('abc', [null, undefined, 'ABC-123'])).toBe(true);
    expect(matchesSearchQuery('missing', [null, undefined])).toBe(false);
  });

  it('supports numeric identifiers and empty queries', () => {
    expect(matchesSearchQuery('927', [9271])).toBe(true);
    expect(matchesSearchQuery('  ', [null])).toBe(true);
  });
});
