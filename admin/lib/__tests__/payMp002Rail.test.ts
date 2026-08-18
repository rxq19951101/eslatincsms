import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet, apiPost } from '../api';
import {
  closeRuntimeRail,
  decideRuntimeRailReopen,
  getRuntimeRails,
  requestRuntimeRailReopen,
} from '../payMp002';
import { PAY_MP_002_MEDIA_TYPE } from '../payMp002Types';

vi.mock('../api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  ApiRequestError: class ApiRequestError extends Error {
    status = 500;
  },
}));

const mockedApiGet = vi.mocked(apiGet);
const mockedApiPost = vi.mocked(apiPost);

describe('PAY-MP-002 FE-210 rail adapter', () => {
  beforeEach(() => vi.clearAllMocks());

  it('keeps both axes and fail-closed unknown status while rebuilding the allowlist', async () => {
    mockedApiGet.mockResolvedValueOnce({
      items: [
        {
          control_id: 'admission-1', axis: 'paid_admission',
          scope: { type: 'platform', ref: 'platform:eslatin' }, status: 'closed',
          reason: 'incident', incident_reference: 'INC-1', effective_at: null,
          closed_by: null, reopened_by: null, health_check_reference: null,
          allowed_actions: ['read', 'request_reopen'], version: 2,
          created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:00:00Z',
          pan: '4111', raw_provider_payload: { token: 'secret' }, unknown: true,
        },
        {
          control_id: 'creation-1', axis: 'payment_creation',
          scope: { type: 'tenant', ref: 'tenant:tenant-1' }, status: 'future',
          reason: null, incident_reference: null, effective_at: null,
          closed_by: null, reopened_by: null, health_check_reference: null,
          allowed_actions: ['read'], version: 1,
          created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:00:00Z',
        },
      ],
      page: { next_cursor: null, has_more: false },
    });

    const page = await getRuntimeRails({ scope_type: 'platform', scope_id: 'platform:eslatin', limit: 50 });
    expect(page.items.map((item) => [item.axis, item.status])).toEqual([
      ['paid_admission', 'closed'], ['payment_creation', 'unknown'],
    ]);
    expect(page.items[0]).not.toHaveProperty('pan');
    expect(page.items[0]).not.toHaveProperty('raw_provider_payload');
    expect(mockedApiGet).toHaveBeenCalledWith(
      '/api/v1/admin/runtime-rails?scope_type=platform&scope_id=platform%3Aeslatin&limit=50',
      expect.objectContaining({ skipTenantId: true, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }),
    );
  });

  it('sends versioned close and different-actor reopen intents through frozen paths', async () => {
    mockedApiPost
      .mockResolvedValueOnce({ control_id: 'control-1', axis: 'payment_creation', scope: { type: 'platform', ref: 'platform:eslatin' }, status: 'closed', reason: 'r', incident_reference: 'i', effective_at: null, closed_by: null, reopened_by: null, health_check_reference: null, allowed_actions: ['read', 'request_reopen'], version: 1, created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:00:00Z' })
      .mockResolvedValueOnce({ request_id: 'request-1', control_id: 'control-1', status: 'requested', reason: 'r', initiator: null, approver: null, health_check_reference: 'health-1', control_status: 'closed', expires_at: '2026-08-16T13:00:00Z', decided_at: null, allowed_actions: ['approve', 'reject'], version: 1, created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:00:00Z' })
      .mockResolvedValueOnce({ request_id: 'request-1', control_id: 'control-1', status: 'rejected', reason: 'r', initiator: null, approver: null, health_check_reference: 'health-1', control_status: 'closed', expires_at: '2026-08-16T13:00:00Z', decided_at: '2026-08-16T12:02:00Z', allowed_actions: ['read'], version: 2, created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:02:00Z' });

    await closeRuntimeRail({ axis: 'payment_creation', scope: { type: 'platform', ref: 'platform:eslatin' }, reason: 'r', incident_reference: 'i', expected_version: 0 }, 'close-1');
    await requestRuntimeRailReopen('control-1', { reason: 'r', health_check_reference: 'health-1', expected_version: 1 }, 'request-1');
    await decideRuntimeRailReopen('request-1', { decision: 'reject', reason: 'r', expected_version: 1 }, 'decision-1');

    expect(mockedApiPost).toHaveBeenNthCalledWith(1, '/api/v1/admin/runtime-rails/close-requests', expect.objectContaining({ expected_version: 0 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'close-1' } }));
    expect(mockedApiPost).toHaveBeenNthCalledWith(2, '/api/v1/admin/runtime-rails/control-1/reopen-requests', expect.objectContaining({ expected_version: 1 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'request-1' } }));
    expect(mockedApiPost).toHaveBeenNthCalledWith(3, '/api/v1/admin/runtime-rail-reopen-requests/request-1/decisions', expect.objectContaining({ decision: 'reject', expected_version: 1 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'decision-1' } }));
  });
});
