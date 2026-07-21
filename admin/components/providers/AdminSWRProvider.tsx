'use client';

import type { ReactNode } from 'react';
import { SWRConfig } from 'swr';
import { ApiRequestError } from '@/lib/api';

export function shouldRetryAdminRequest(error: unknown): boolean {
  return !(error instanceof ApiRequestError && error.status >= 400 && error.status < 500);
}

export function AdminSWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        dedupingInterval: 5000,
        revalidateOnFocus: false,
        refreshWhenHidden: false,
        refreshWhenOffline: false,
        shouldRetryOnError: shouldRetryAdminRequest,
        onErrorRetry: (error, _key, _config, revalidate, options) => {
          if (!shouldRetryAdminRequest(error)) return;
          if (options.retryCount >= 3) return;
          const delay = Math.min(1000 * (2 ** options.retryCount), 10000);
          setTimeout(() => void revalidate({ retryCount: options.retryCount }), delay);
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
