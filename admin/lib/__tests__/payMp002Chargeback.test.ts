import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet } from '../api';
import { getAuditEvents, getChargebackCase, getChargebackCases } from '../payMp002';
import { PAY_MP_002_MEDIA_TYPE } from '../payMp002Types';

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

describe('PAY-MP-002 FE-209A read-only adapters', () => {
  beforeEach(() => vi.clearAllMocks());

  it('decodes chargeback list/detail projections with deadline, funds state, unknown status and no sensitive fields', async () => {
    const projection = {
      case_id: 'cb-1', payment_reference: 'payment-1', invoice_reference: 'invoice-1', amount: '3331.80', currency: 'COP',
      status: 'future_provider_state', deadline_at: '2026-08-20T12:00:00Z', funds_state: 'held',
      timeline: [{ event_id: 'event-1', type: 'chargeback.hold', status: 'hold', occurred_at: '2026-08-16T12:00:00Z', actor: null, reason_code: 'funds_held', reference: 'audit-1', raw_provider_payload: { pan: 'blocked' } }],
      allowed_actions: ['view', 'refresh'], version: 4, created_at: '2026-08-16T11:00:00Z', updated_at: '2026-08-16T12:00:00Z',
      pan: '4111111111111111', cvv: '123', raw_provider_payload: { token: 'blocked' }, unknown_field: 'blocked',
    };
    mockedApiGet.mockResolvedValueOnce({ items: [projection], page: { next_cursor: 'cb-next', has_more: true } });
    mockedApiGet.mockResolvedValueOnce(projection);

    const page = await getChargebackCases({ status: 'hold', deadline_from: '2026-08-16T00:00:00Z', deadline_to: '2026-08-21T00:00:00Z', cursor: 'cb-cursor', limit: 20 });
    const detail = await getChargebackCase('cb-1');

    expect(page.items[0]).toMatchObject({ case_id: 'cb-1', amount: '3331.80', status: 'unknown', deadline_at: '2026-08-20T12:00:00Z', funds_state: 'held', version: 4 });
    expect(page.items[0]).not.toHaveProperty('pan');
    expect(page.items[0]).not.toHaveProperty('unknown_field');
    expect(page.items[0].timeline[0]).not.toHaveProperty('raw_provider_payload');
    expect(detail).toEqual(page.items[0]);
    expect(mockedApiGet).toHaveBeenNthCalledWith(1, '/api/v1/admin/chargeback-cases?status=hold&deadline_from=2026-08-16T00%3A00%3A00Z&deadline_to=2026-08-21T00%3A00%3A00Z&cursor=cb-cursor&limit=20', expect.objectContaining({ skipTenantId: false, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }));
    expect(mockedApiGet).toHaveBeenNthCalledWith(2, '/api/v1/admin/chargeback-cases/cb-1', expect.objectContaining({ skipTenantId: false, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }));
  });

  it('keeps AuditEvent at the frozen read-only adapter boundary and filters safe metadata', async () => {
    mockedApiGet.mockResolvedValueOnce({
      items: [{
        event_id: 'audit-1', actor: { id: 'actor-1', display_name: 'Ops', role_label: 'operations', cvv: 'blocked' },
        resource: { type: 'chargeback_case', id: 'cb-1', pan: 'blocked' }, action: 'view', result: 'success',
        scope: { type: 'tenant', ref: 'tenant:tenant-1' }, reason_code: 'manual_review',
        safe_metadata: {
          source: 'admin', count: 1,
          PAN: 'blocked', PANNumber: 'blocked', CVV: 'blocked', token: 'blocked', secret: 'blocked',
          raw_provider_payload: 'blocked', rawProviderPayload: 'blocked', provider_payload: 'blocked', providerPayload: 'blocked',
          nested: {
            'pan-number': 'blocked', 'CVV2': 'blocked', safe: 'retained',
            values: [{ rawProviderPayload: 'blocked', providerPayload: 'blocked', safe: 'retained' }],
          },
        },
        occurred_at: '2026-08-16T12:00:00Z', unknown_field: 'blocked',
      }], page: { next_cursor: null, has_more: false },
    });

    const page = await getAuditEvents({ actor: 'actor-1', resource_type: 'chargeback_case', resource_id: 'cb-1', action: 'view', result: 'success', from: '2026-08-16T00:00:00Z', to: '2026-08-17T00:00:00Z', cursor: 'audit-cursor', limit: 20 });
    expect(page.items[0]).toEqual({
      event_id: 'audit-1', actor: { id: 'actor-1', display_name: 'Ops', role_label: 'operations' },
      resource: { type: 'chargeback_case', id: 'cb-1' }, action: 'view', result: 'success',
      scope: { type: 'tenant', ref: 'tenant:tenant-1' }, reason_code: 'manual_review',
      safe_metadata: { source: 'admin', count: 1, nested: { safe: 'retained', values: [{ safe: 'retained' }] } }, occurred_at: '2026-08-16T12:00:00Z',
    });
    expect(mockedApiGet).toHaveBeenCalledWith('/api/v1/admin/audit-events?actor=actor-1&resource_type=chargeback_case&resource_id=cb-1&action=view&result=success&from=2026-08-16T00%3A00%3A00Z&to=2026-08-17T00%3A00%3A00Z&cursor=audit-cursor&limit=20', expect.objectContaining({ skipTenantId: false, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }));
  });
});
