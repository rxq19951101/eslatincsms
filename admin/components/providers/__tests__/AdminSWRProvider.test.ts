import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '@/lib/api';
import { shouldRetryAdminRequest } from '../AdminSWRProvider';

describe('Admin SWR retry policy', () => {
  it.each([400, 401, 403, 404, 409, 422, 429])(
    'does not retry HTTP %s',
    (status) => {
      expect(shouldRetryAdminRequest(new ApiRequestError('request failed', status))).toBe(false);
    }
  );

  it('retries server and network failures', () => {
    expect(shouldRetryAdminRequest(new ApiRequestError('server failed', 503))).toBe(true);
    expect(shouldRetryAdminRequest(new Error('network failed'))).toBe(true);
  });
});
