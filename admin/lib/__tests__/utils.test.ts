import { describe, it, expect } from 'vitest';
import { cn } from '../utils';

describe('cn (class name utility)', () => {
  it('应该合并多个类名', () => {
    const result = cn('foo', 'bar');
    expect(result).toBe('foo bar');
  });

  it('应该处理条件类名', () => {
    const result = cn('foo', false && 'bar', 'baz');
    expect(result).toBe('foo baz');
  });

  it('应该合并 Tailwind 冲突的类名', () => {
    const result = cn('p-4', 'p-6');
    expect(result).toBe('p-6');
  });

  it('应该处理 undefined 和 null', () => {
    const result = cn('foo', undefined, null, 'bar');
    expect(result).toBe('foo bar');
  });
});