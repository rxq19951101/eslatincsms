import '@testing-library/jest-dom';
import { expect, afterEach, vi, beforeAll, afterAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
import React, { type ImgHTMLAttributes } from 'react';
import { server } from './__mocks__/server';

expect.extend(matchers);

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  if (typeof window !== 'undefined') {
    window.localStorage.clear();
  }
  vi.clearAllMocks();
});

afterAll(() => {
  server.close();
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
    src: string | { src: string };
  }) => {
    const normalizedSrc = typeof src === 'string' ? src : src.src;
    return React.createElement('img', { src: normalizedSrc, alt, ...props });
  },
}));
