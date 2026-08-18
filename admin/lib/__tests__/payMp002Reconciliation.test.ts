import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet, apiPost } from '../api';
import {
  createReconciliationExport,
  createResolutionIntent,
  decideTemporaryAcceptance,
  getReconciliationExceptions,
  getReconciliationExport,
  getReconciliationItems,
  getReconciliationRun,
  requestTemporaryAcceptance,
  safeReconciliationDownloadPath,
  reconciliationCsvFilename,
} from '../payMp002';
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
const mockedApiPost = vi.mocked(apiPost);

describe('PAY-MP-002 FE-208 reconciliation adapter', () => {
  beforeEach(() => vi.clearAllMocks());

  it('decodes a run detail without exposing unknown backend fields', async () => {
    mockedApiGet.mockResolvedValueOnce({
      run_id: 'run-1',
      business_date: '2026-08-16',
      run_type: 'daily',
      status: 'completed_with_exceptions',
      cutoff_at: '2026-08-16T03:00:00Z',
      closed_at: null,
      source_watermarks: { eslatin: 'wm-1', raw_provider_payload: 'blocked' },
      item_count: 4,
      matched_count: 3,
      exception_count: 1,
      provider: 'mercadopago',
      secret: 'blocked',
      version: 4,
      created_at: '2026-08-16T01:00:00Z',
      updated_at: '2026-08-16T03:00:00Z',
      allowed_actions: ['view', 'refresh'],
    });

    const run = await getReconciliationRun('run-1', 'tenant:tenant-1');
    expect(run.summary).toEqual({ item_count: 4, matched_count: 3, exception_count: 1 });
    expect(run).not.toHaveProperty('provider');
    expect(run.source_watermarks).toEqual({ eslatin: 'wm-1' });
    expect(mockedApiGet).toHaveBeenCalledWith(
      '/api/v1/admin/reconciliation/runs/run-1?tenant_scope=tenant%3Atenant-1',
      expect.objectContaining({ skipTenantId: true, headers: { Accept: PAY_MP_002_MEDIA_TYPE } }),
    );
  });

  it('keeps item and exception cursors in the frozen query contract', async () => {
    mockedApiGet
      .mockResolvedValueOnce({
        items: [{
          item_id: 'item-1', run_id: 'run-1',
          references: { eslatin: 'inv-1', provider: 'provider-1', funds: 'funds-1', pan: 'blocked' },
          amounts: { expected: '100.00', provider: '100.00' }, currency: 'COP', status: 'mismatch',
          mismatch_code: 'amount_mismatch', raw_provider_payload: 'blocked', allowed_actions: ['view'],
          version: 2, created_at: '2026-08-16T01:00:00Z', updated_at: '2026-08-16T01:01:00Z',
        }], page: { next_cursor: 'next-item', has_more: true },
      })
      .mockResolvedValueOnce({
        items: [{
          exception_id: 'exception-1', item_id: 'item-1', status: 'mismatch', difference_type: 'timing',
          difference_amount: '1.00', currency: 'COP', owner_ref: 'finance', severity: 'high',
          due_at: '2026-08-17T00:00:00Z', temporary_acceptance_until: null,
          allowed_actions: ['view', 'resolve', 'request_temporary_acceptance'], version: 3,
          created_at: '2026-08-16T01:00:00Z', updated_at: '2026-08-16T01:01:00Z',
        }], page: { next_cursor: null, has_more: false },
      });

    const items = await getReconciliationItems({ runId: 'run-1', status: 'mismatch', cursor: 'item-cursor', limit: 20, tenant_scope: 'tenant:tenant-1' });
    const exceptions = await getReconciliationExceptions({ cursor: 'exception-cursor', limit: 20, tenant_scope: 'tenant:tenant-1' });

    expect(items.items[0]).toMatchObject({ eslatin_reference: 'inv-1', amount: '100.00', match_status: 'mismatch' });
    expect(items.items[0]).not.toHaveProperty('pan');
    expect(exceptions.items[0]).toMatchObject({ category: 'timing', owner: 'finance', status: 'mismatch' });
    expect(mockedApiGet).toHaveBeenNthCalledWith(1, '/api/v1/admin/reconciliation/runs/run-1/items?status=mismatch&cursor=item-cursor&limit=20&tenant_scope=tenant%3Atenant-1', expect.anything());
    expect(mockedApiGet).toHaveBeenNthCalledWith(2, '/api/v1/admin/reconciliation/exceptions?cursor=exception-cursor&limit=20&tenant_scope=tenant%3Atenant-1', expect.anything());
  });

  it('keeps resolution and temporary acceptance as server intents', async () => {
    mockedApiPost
      .mockResolvedValueOnce({
        intent_id: 'intent-1', exception_id: 'exception-1', resolution_code: 'timing_review',
        reason: 'review evidence', status: 'pending', initiator: null, allowed_actions: ['view'], version: 1,
        created_at: '2026-08-16T01:00:00Z', updated_at: '2026-08-16T01:00:00Z',
        item_id: 'must-not-leak', pan: '4111111111111111', raw_provider_payload: { secret: true },
      })
      .mockResolvedValueOnce({
        request_id: 'request-1', exception_id: 'exception-1', status: 'pending', reason: 'bounded timing review',
        initiator: { id: 'actor-1', display_name: 'Finance', role_label: 'finance', cvv: '123' }, approver: null,
        expires_at: '2026-08-17T01:00:00Z', decided_at: null, allowed_actions: ['view', 'approve'], version: 2,
        created_at: '2026-08-16T01:00:00Z', updated_at: '2026-08-16T01:01:00Z',
        category: 'must-not-leak', raw_provider_payload: { secret: true },
      })
      .mockResolvedValueOnce({
        request_id: 'request-1', exception_id: 'exception-1', status: 'temporarily_accepted', reason: 'approved timing window',
        initiator: { id: 'actor-1', display_name: 'Finance', role_label: 'finance' },
        approver: { id: 'actor-2', display_name: 'Platform', role_label: 'platform' },
        expires_at: '2026-08-17T01:00:00Z', decided_at: '2026-08-16T02:00:00Z', allowed_actions: ['view'], version: 3,
        status_detail: 'must-not-leak', cvv: '123',
        created_at: '2026-08-16T01:00:00Z', updated_at: '2026-08-16T02:00:00Z',
      });

    const intent = await createResolutionIntent('exception-1', { resolution_code: 'timing_review', reason: 'review evidence', expected_version: 3 }, 'idem-1');
    const request = await requestTemporaryAcceptance('exception-1', { reason: 'bounded timing review', expected_version: 4 }, 'idem-2');
    const decision = await decideTemporaryAcceptance('request-1', { decision: 'approve', reason: 'approved timing window', expected_version: 2 }, 'idem-3');

    expect(mockedApiPost).toHaveBeenNthCalledWith(1, '/api/v1/admin/reconciliation/exceptions/exception-1/resolution-intents', expect.objectContaining({ expected_version: 3 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'idem-1' }, skipTenantId: true }));
    expect(mockedApiPost).toHaveBeenNthCalledWith(2, '/api/v1/admin/reconciliation/exceptions/exception-1/temporary-acceptance-requests', expect.objectContaining({ expected_version: 4 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'idem-2' }, skipTenantId: true }));
    expect(mockedApiPost).toHaveBeenNthCalledWith(3, '/api/v1/admin/reconciliation/temporary-acceptance-requests/request-1/decisions', expect.objectContaining({ decision: 'approve', expected_version: 2 }), expect.objectContaining({ headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': 'idem-3' }, skipTenantId: true }));
    expect(mockedApiPost.mock.calls[0][1]).not.toHaveProperty('status', 'matched');
    expect(intent).toMatchObject({ intent_id: 'intent-1', exception_id: 'exception-1', resolution_code: 'timing_review', reason: 'review evidence', status: 'pending' });
    expect(intent).not.toHaveProperty('item_id');
    expect(intent).not.toHaveProperty('pan');
    expect(request).toMatchObject({ request_id: 'request-1', exception_id: 'exception-1', status: 'pending', reason: 'bounded timing review', expires_at: '2026-08-17T01:00:00Z' });
    expect(request.initiator).toMatchObject({ id: 'actor-1', display_name: 'Finance' });
    expect(request.initiator).not.toHaveProperty('cvv');
    expect(request).not.toHaveProperty('category');
    expect(decision).toMatchObject({ request_id: 'request-1', status: 'temporarily_accepted', decided_at: '2026-08-16T02:00:00Z' });
    expect(decision.approver).toMatchObject({ id: 'actor-2', display_name: 'Platform' });
    expect(decision).not.toHaveProperty('status_detail');
    expect(decision).not.toHaveProperty('cvv');
  });

  it('enforces the CSV lifecycle presentation boundary', async () => {
    mockedApiPost.mockResolvedValueOnce({
      export_id: 'export-1', status: 'queued', download_path: null,
      expires_at: '2026-08-16T04:00:00Z', audit_reference: 'audit-export-1', version: 1,
      created_at: '2026-08-16T03:00:00Z', updated_at: '2026-08-16T03:00:00Z',
    });
    mockedApiGet.mockResolvedValueOnce({
      export_id: 'export-1', status: 'ready', download_path: '/api/v1/admin/reconciliation/exports/export-1/download',
      expires_at: '2026-08-16T04:00:00Z', audit_reference: 'audit-export-1', version: 2,
      created_at: '2026-08-16T03:00:00Z', updated_at: '2026-08-16T03:01:00Z',
    });

    const queued = await createReconciliationExport('run-1', { status: ['mismatch'] }, 'export-idem');
    const ready = await getReconciliationExport('export-1');
    expect(queued.status).toBe('queued');
    expect(ready.status).toBe('ready');
    expect(safeReconciliationDownloadPath(ready.download_path)).toBe('/api/v1/admin/reconciliation/exports/export-1/download');
    expect(safeReconciliationDownloadPath('https://provider.example/export.csv')).toBeNull();
    expect(reconciliationCsvFilename('export-1')).toBe('reconciliation-export-1.csv');
    expect(ready.audit_reference).toBe('audit-export-1');
  });
});
