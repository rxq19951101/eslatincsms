import '@testing-library/jest-dom';
import { expect, afterEach, vi, beforeAll, afterAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
import { server } from './__mocks__/server';

expect.extend(matchers);

// 创建 localStorage mock
const createLocalStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (index: number) => {
      const keys = Object.keys(store);
      return keys[index] || null;
    },
  };
};

// 在测试环境初始化时设置 localStorage
if (typeof window !== 'undefined') {
  const localStorageMock = createLocalStorageMock();
  Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
    writable: true,
    configurable: true,
  });
  
  // 也设置全局 localStorage（某些情况下需要）
  (global as any).localStorage = localStorageMock;
}

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  // 清理 localStorage
  if (typeof window !== 'undefined' && window.localStorage && typeof window.localStorage.clear === 'function') {
    window.localStorage.clear();
  } else if (typeof window !== 'undefined' && (window as any).localStorage) {
    // 如果 clear 不存在，手动清除
    const storage = (window as any).localStorage;
    if (storage && typeof storage.getItem === 'function') {
      const keys: string[] = [];
      for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i);
        if (key) keys.push(key);
      }
      keys.forEach(key => storage.removeItem(key));
    }
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
  default: ({ src, alt, ...props }: any) => {
    const React = require('react');
    return React.createElement('img', { src, alt, ...props });
  },
}));