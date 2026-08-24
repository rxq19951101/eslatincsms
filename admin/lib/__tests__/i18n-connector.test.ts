import { describe, expect, it } from 'vitest';

import { translateMessage } from '@/lib/i18n';

describe('connector fallback labels', () => {
  it('uses one stable connector number across all supported locales', () => {
    expect(translateMessage('zh-CN', '充电枪 2')).toBe('充电枪 2');
    expect(translateMessage('en', '充电枪 2')).toBe('Connector 2');
    expect(translateMessage('es', '充电枪 2')).toBe('Conector 2');
  });
});
