import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet, apiPost } from '../api';
import {
  closeRuntimeRail,
  decideRuntimeRailReopen,
  getRefundCases,
  getAuditEvents,
  getChargebackCases,
  getReconciliationRuns,
  getRuntimeRails,
  getSupportCases,
  PayMp002AdminError,
  postP002Intent,
  requestRuntimeRailReopen,
} from '../payMp002';
import { PAY_MP_002_MEDIA_TYPE } from '../payMp002Types';
import { adminResourceViewState, normalizeAdminStatus, normalizeApprovalStatus } from '../payMp002Status';

vi.mock('../api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  ApiRequestError: class ApiRequestError extends Error {
    status: number;
    retryAfterMs?: number;
    constructor(message: string, status: number, _fields = {}, retryAfterMs?: number) {
      super(message);
      this.status = status;
      this.retryAfterMs = retryAfterMs;
    }
  },
}));

const mockedApiGet = vi.mocked(apiGet);
const mockedApiPost = vi.mocked(apiPost);

describe('PAY-MP-002 Admin FE-201 adapter', () => {
  beforeEach(() => vi.clearAllMocks());

  it('requests cursor pages with the frozen media type and no client tenant header', async () => {
    mockedApiGet.mockResolvedValueOnce({ items: [], page: { next_cursor: null, has_more: false } });

    await expect(getRefundCases({ cursor: 'cursor-1', limit: 20 })).resolves.toEqual({
      items: [], page: { next_cursor: null, has_more: false },
    });
    expect(mockedApiGet).toHaveBeenCalledWith(
      '/api/v1/admin/refund-cases?cursor=cursor-1&limit=20',
      expect.objectContaining({
        skipTenantId: true,
        headers: { Accept: PAY_MP_002_MEDIA_TYPE },
      }),
    );
  });

  it('maps unknown Admin enums to unknown and preserves loading/recovery semantics', () => {
    expect(normalizeAdminStatus('future_status')).toBe('unknown');
    expect(normalizeApprovalStatus('future_approval')).toBe('unknown');
    expect(adminResourceViewState('provider_processing')).toBe('processing');
    expect(adminResourceViewState('manual_review')).toBe('recovery');
  });

  it('rebuilds Admin projections from allowlisted fields only', async () => {
    mockedApiGet
      .mockResolvedValueOnce({
        items: [{
          case_id: 'case-1',
          target: {
            resource_type: 'invoice', resource_id: 'invoice-1', pan: '4111111111111111',
          },
          requested_amount: '100.00',
          approved_amount: null,
          confirmed_refunded_amount: '0.00',
          currency: 'COP',
          status: 'submitted',
          approval: {
            status: 'pending',
            initiator: { id: 'actor-1', display_name: 'Ops', role_label: 'operations', cvv: '123' },
            approver: null,
            requested_at: '2026-08-13T12:00:00Z',
            decided_at: null,
            expires_at: null,
            version: 1,
            raw_provider_payload: { token: 'secret' },
          },
          provider_reference: 'provider-ref',
          timeline: [{
            event_id: 'event-1', type: 'refund.submitted', status: 'submitted',
            occurred_at: '2026-08-13T12:00:00Z', actor: null, reason_code: null, reference: 'ref-1',
            raw_provider_payload: { pan: '4111111111111111' },
          }],
          audit_references: ['audit-1'],
          allowed_actions: ['view'],
          version: 1,
          created_at: '2026-08-13T12:00:00Z',
          updated_at: '2026-08-13T12:00:00Z',
          pan: '4111111111111111',
          cvv: '123',
          raw_provider_payload: { token: 'secret' },
        }],
        page: { next_cursor: null, has_more: false },
      })
      .mockResolvedValueOnce({
        items: [{
          control_id: 'control-1',
          axis: 'paid_admission',
          scope: { type: 'platform', ref: 'platform:eslatin', cvv: '123' },
          status: 'open',
          reason: null,
          incident_reference: null,
          effective_at: '2026-08-13T12:00:00Z',
          closed_by: { id: 'actor-1', display_name: 'Ops', role_label: 'operations', pan: '4111111111111111' },
          reopened_by: null,
          health_check_reference: null,
          allowed_actions: ['view'],
          version: 1,
          created_at: '2026-08-13T12:00:00Z',
          updated_at: '2026-08-13T12:00:00Z',
          raw_provider_payload: { token: 'secret' },
        }],
        page: { next_cursor: null, has_more: false },
      })
      .mockResolvedValueOnce({
        items: [{
          case_id: 'support-1',
          reference: 'SUP-1',
          status: 'open',
          category: 'payment_recovery',
          linked_resources: [{ type: 'invoice', id: 'invoice-1', reference: 'INV-1', cvv: '123' }],
          sla_target_at: '2026-08-13T13:00:00Z',
          assignee: { id: 'actor-1', display_name: 'Ops', role_label: 'operations', pan: '4111111111111111' },
          timeline: [{
            event_id: 'event-2', type: 'support.open', status: 'open',
            occurred_at: '2026-08-13T12:00:00Z', actor: null, reason_code: null, reference: 'ref-2',
            raw_provider_payload: { cvv: '123' },
          }],
          allowed_actions: ['view'],
          version: 1,
          created_at: '2026-08-13T12:00:00Z',
          updated_at: '2026-08-13T12:00:00Z',
          pan: '4111111111111111',
          cvv: '123',
          raw_provider_payload: { token: 'secret' },
        }],
        page: { next_cursor: null, has_more: false },
      });

    const refunds = await getRefundCases();
    const rails = await getRuntimeRails();
    const support = await getSupportCases();

    expect(refunds.items[0]).not.toHaveProperty('pan');
    expect(refunds.items[0]).not.toHaveProperty('cvv');
    expect(refunds.items[0]).not.toHaveProperty('raw_provider_payload');
    expect(refunds.items[0].target).not.toHaveProperty('pan');
    expect(refunds.items[0].approval.initiator).not.toHaveProperty('cvv');
    expect(refunds.items[0].timeline[0]).not.toHaveProperty('raw_provider_payload');

    expect(rails.items[0]).not.toHaveProperty('raw_provider_payload');
    expect(rails.items[0].scope).not.toHaveProperty('cvv');
    expect(rails.items[0].closed_by).not.toHaveProperty('pan');

    expect(support.items[0]).not.toHaveProperty('pan');
    expect(support.items[0]).not.toHaveProperty('cvv');
    expect(support.items[0]).not.toHaveProperty('raw_provider_payload');
    expect(support.items[0].linked_resources[0]).not.toHaveProperty('cvv');
    expect(support.items[0].assignee).not.toHaveProperty('pan');
    expect(support.items[0].timeline[0]).not.toHaveProperty('raw_provider_payload');
  });

  it('keeps failed list responses as errors instead of empty lists', async () => {
    mockedApiGet.mockRejectedValueOnce(new (class extends Error {
      status = 503;
      retryAfterMs = 1000;
    })('offline'));
    await expect(getSupportCases()).rejects.toBeInstanceOf(PayMp002AdminError);
  });

  it('exposes the remaining FE-206 list adapters with the same frozen media type', async () => {
    const page = { items: [], page: { next_cursor: null, has_more: false } };
    mockedApiGet
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce(page);

    await getChargebackCases({ cursor: 'cb-1', limit: 20 });
    await getReconciliationRuns({ cursor: 'recon-1', limit: 20 });
    await getAuditEvents({ cursor: 'audit-1', limit: 20 });

    expect(mockedApiGet).toHaveBeenNthCalledWith(
      1,
      '/api/v1/admin/chargeback-cases?cursor=cb-1&limit=20',
      expect.objectContaining({ skipTenantId: false, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }),
    );
    expect(mockedApiGet).toHaveBeenNthCalledWith(
      2,
      '/api/v1/admin/reconciliation/runs?cursor=recon-1&limit=20',
      expect.objectContaining({ skipTenantId: true, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }),
    );
    expect(mockedApiGet).toHaveBeenNthCalledWith(
      3,
      '/api/v1/admin/audit-events?cursor=audit-1&limit=20',
      expect.objectContaining({ skipTenantId: false, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }),
    );
  });

  it('requires an idempotency key for all Admin write intents', async () => {
    await expect(postP002Intent('/admin/refund-cases', {}, ' ')).rejects.toMatchObject({
      canonical: expect.objectContaining({ code: 'REQUEST_INVALID' }),
    });
    expect(mockedApiPost).not.toHaveBeenCalled();
  });

  it('sends the frozen Accept and Idempotency-Key headers for a write intent', async () => {
    mockedApiPost.mockResolvedValueOnce({ case_id: 'case-1' });
    await postP002Intent('/admin/refund-cases', { reason: 'customer_request' }, 'idem-1');
    expect(mockedApiPost).toHaveBeenCalledWith(
      '/api/v1/admin/refund-cases',
      { reason: 'customer_request' },
      expect.objectContaining({
        skipTenantId: true,
        headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'idem-1' },
      }),
    );
  });

  it('uses the frozen rail endpoints and rebuilds rail/reopen projections from allowlisted fields', async () => {
    mockedApiPost
      .mockResolvedValueOnce({
        control_id: 'control-1', axis: 'paid_admission',
        scope: { type: 'platform', ref: 'platform:eslatin', pan: '4111' }, status: 'closed',
        reason: 'incident', incident_reference: 'INC-1', effective_at: '2026-08-16T12:00:00Z',
        closed_by: { id: 'actor-1', display_name: 'Ops', role_label: 'platform', cvv: '123' },
        reopened_by: null, health_check_reference: null, allowed_actions: ['read', 'request_reopen'],
        version: 2, created_at: '2026-08-16T12:00:00Z', updated_at: '2026-08-16T12:00:00Z',
        raw_provider_payload: { token: 'secret' }, unknown_field: 'drop-me',
      })
      .mockResolvedValueOnce({
        request_id: 'request-1', control_id: 'control-1', status: 'requested', reason: 'mitigated',
        initiator: { id: 'actor-1', display_name: 'Ops', role_label: 'platform', pan: '4111' },
        approver: null, health_check_reference: 'health-1', control_status: 'closed',
        expires_at: '2026-08-16T13:00:00Z', decided_at: null, allowed_actions: ['approve', 'reject'],
        version: 1, created_at: '2026-08-16T12:01:00Z', updated_at: '2026-08-16T12:01:00Z',
        raw_provider_payload: { cvv: '123' }, unknown_field: 'drop-me',
      })
      .mockResolvedValueOnce({
        request_id: 'request-1', control_id: 'control-1', status: 'approved', reason: 'health passed',
        initiator: { id: 'actor-1', display_name: 'Ops', role_label: 'platform' },
        approver: { id: 'actor-2', display_name: 'Finance', role_label: 'platform' },
        health_check_reference: 'health-1', control_status: 'open',
        expires_at: '2026-08-16T13:00:00Z', decided_at: '2026-08-16T12:02:00Z', allowed_actions: ['read'],
        version: 2, created_at: '2026-08-16T12:01:00Z', updated_at: '2026-08-16T12:02:00Z',
      });

    const closed = await closeRuntimeRail({
      axis: 'paid_admission',
      scope: { type: 'platform', ref: 'platform:eslatin' },
      reason: 'incident', incident_reference: 'INC-1', expected_version: 1,
    }, 'close-1');
    const requested = await requestRuntimeRailReopen('control-1', {
      reason: 'mitigated', health_check_reference: 'health-1', expected_version: 2,
    }, 'reopen-1');
    const decided = await decideRuntimeRailReopen('request-1', {
      decision: 'approve', reason: 'health passed', expected_version: 1,
    }, 'decision-1');

    expect(closed).toMatchObject({ control_id: 'control-1', axis: 'paid_admission', status: 'closed', version: 2 });
    expect(closed).not.toHaveProperty('raw_provider_payload');
    expect(closed.scope).toEqual({ type: 'platform', ref: 'platform:eslatin' });
    expect(closed.closed_by).toEqual({ id: 'actor-1', display_name: 'Ops', role_label: 'platform' });
    expect(requested).toMatchObject({ request_id: 'request-1', status: 'requested', control_status: 'closed' });
    expect(requested.initiator).toEqual({ id: 'actor-1', display_name: 'Ops', role_label: 'platform' });
    expect(decided).toMatchObject({ request_id: 'request-1', status: 'approved', control_status: 'open', version: 2 });

    expect(mockedApiPost).toHaveBeenNthCalledWith(
      1,
      '/api/v1/admin/runtime-rails/close-requests',
      expect.objectContaining({ axis: 'paid_admission', expected_version: 1 }),
      expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'close-1' }, skipTenantId: true }),
    );
    expect(mockedApiPost).toHaveBeenNthCalledWith(
      2,
      '/api/v1/admin/runtime-rails/control-1/reopen-requests',
      expect.objectContaining({ expected_version: 2 }),
      expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'reopen-1' }, skipTenantId: true }),
    );
    expect(mockedApiPost).toHaveBeenNthCalledWith(
      3,
      '/api/v1/admin/runtime-rail-reopen-requests/request-1/decisions',
      expect.objectContaining({ decision: 'approve', expected_version: 1 }),
      expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'decision-1' }, skipTenantId: true }),
    );
  });
});
