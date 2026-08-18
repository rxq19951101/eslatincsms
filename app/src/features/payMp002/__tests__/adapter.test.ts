import apiClient from '../../../api/client';
import {
  getP001Transactions,
  getP002TransactionDetail,
  getP002Transactions,
  getSupportCases,
  getUnpaidInvoice,
  getUnpaidInvoices,
  isAllowedHostedUrl,
  normalizeFinancialEligibility,
  normalizeRecoveryAttempt,
  PayMp002Error,
} from '../adapter';
import { recoveryProjectionViewState, normalizeAllocationStatus, normalizeEligibilityStatus, normalizeRecoveryStatus } from '../status';
import { PAY_MP_002_MEDIA_TYPE } from '../types';

jest.mock('../../../api/client', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('PAY-MP-002 App FE-201 adapter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('keeps P001 bare-array compatibility and does not send the P002 Accept header', async () => {
    mockedClient.get.mockResolvedValueOnce({ data: [] });

    await expect(getP001Transactions({ limit: 20, offset: 0 })).resolves.toEqual([]);
    expect(mockedClient.get).toHaveBeenCalledWith(expect.any(String), { params: { limit: 20, offset: 0 } });
  });

  it('uses only the vendor Accept header for P002 cursor transactions', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: { items: [], page: { next_cursor: null, has_more: false } },
    });

    await expect(getP002Transactions({ cursor: 'opaque-cursor', limit: 10 })).resolves.toEqual({
      items: [], page: { next_cursor: null, has_more: false },
    });
    expect(mockedClient.get).toHaveBeenCalledWith(expect.any(String), {
      params: { status: undefined, cursor: 'opaque-cursor', limit: 10 },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
  });

  it('decodes server-owned payment status and invoice facts without changing P001 fields', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        id: 'session-1', transaction_id: 42, charge_point_id: 'charger-1',
        ocpp_identity: 'CP-1', evse_id: 'evse-1',
        start_time: '2026-08-13T12:00:00Z', end_time: '2026-08-13T12:30:00Z',
        status: 'completed', energy_kwh: '6.800', duration_minutes: '30.00',
        site_name: 'Station', site_address: 'Address',
        invoice: {
          id: 'invoice-1', reference: 'INV-1', status: 'paid', amount: '18360.00',
          currency: 'COP', issued_at: '2026-08-13T12:30:00Z',
          paid_at: '2026-08-13T12:31:00Z', pricing_snapshot_reference: null,
        },
        payments: [], payment_status: 'paid', data_quality: 'current',
        support_case_refs: [], allowed_actions: ['view', 'refresh'],
        updated_at: '2026-08-13T12:31:00Z',
      },
    });

    await expect(getP002TransactionDetail('session-1')).resolves.toMatchObject({
      id: 'session-1', payment_status: 'paid', data_quality: 'current',
      invoice: { reference: 'INV-1', amount: '18360.00', currency: 'COP' },
    });
    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/transactions/session-1', {
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
  });

  it('decodes support case projections and preserves safe timeline boundaries', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        items: [{
          case_id: 'case-1', reference: 'SUP-1', status: 'open', category: 'unpaid',
          linked_resources: [{ type: 'invoice', id: 'invoice-1', reference: 'INV-1' }],
          sla_target_at: '2026-08-16T12:00:00Z', assignee: null,
          timeline: [{
            event_id: 'event-1', case_id: 'case-1', event_type: 'case_opened',
            note_visibility: 'user', status: 'open',
            actor: { id: 'app-user', display_name: 'Customer', role_label: 'customer' },
            occurred_at: '2026-08-15T12:00:00Z', case_version: 1,
          }],
          linked_refund_case: null, allowed_actions: ['view'], version: 1,
          created_at: '2026-08-15T12:00:00Z', updated_at: '2026-08-15T12:00:00Z',
          internal_note: 'must not cross boundary',
        }],
        page: { next_cursor: null, has_more: false },
      },
    });

    const result = await getSupportCases({ limit: 10 });
    expect(result.items[0]).toMatchObject({ case_id: 'case-1', status: 'open', reference: 'SUP-1' });
    expect(result.items[0]).not.toHaveProperty('internal_note');
    expect(result.items[0].timeline[0]).toMatchObject({ event_type: 'case_opened', note_visibility: 'user' });
    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/support-cases', {
      params: { status: undefined, cursor: undefined, limit: 10 },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
  });

  it('rejects offset instead of guessing a second pagination contract', async () => {
    await expect(getP002Transactions({ offset: 0 })).rejects.toMatchObject({
      canonical: expect.objectContaining({ code: 'PAGINATION_MODE_INVALID' }),
      httpStatus: 400,
    });
    expect(mockedClient.get).not.toHaveBeenCalled();
  });

  it('decodes the typed unpaid invoice projection without coercing money', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        items: [{
          invoice_id: 'invoice-1', invoice_reference: 'INV-1', session_id: 'session-1',
          site: 'Bogota', charge_point_reference: 'CP-1', connector_id: null,
          started_at: '2026-08-15T10:00:00Z', ended_at: '2026-08-15T10:30:00Z',
          energy_kwh: '0.018', original_amount: '48.60', allocated_amount: '0.00',
          refunded_amount: '0.00', outstanding_amount: '48.60', currency: 'COP',
          blocking_reason: 'open_invoice', recovery_status: null,
          active_recovery_attempt_id: null, d1_status: 'blocked',
          allowed_actions: ['view', 'start_recovery'], updated_at: '2026-08-15T10:30:00Z',
        }],
        page: { next_cursor: null, has_more: false },
      },
    });

    await expect(getUnpaidInvoices()).resolves.toMatchObject({
      items: [{ invoice_id: 'invoice-1', outstanding_amount: '48.60', d1_status: 'blocked' }],
      page: { next_cursor: null, has_more: false },
    });
    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/unpaid-charges', {
      params: { cursor: undefined, limit: undefined },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
  });

  it('decodes recovery methods and keeps the saved-card reference opaque', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        invoice_id: 'invoice-1', invoice_reference: 'INV-1', session_id: 'session-1',
        site: null, charge_point_reference: 'CP-1', connector_id: null,
        started_at: null, ended_at: null, energy_kwh: '1.000', original_amount: '2700.00',
        allocated_amount: '0.00', refunded_amount: '0.00', outstanding_amount: '2700.00',
        currency: 'COP', blocking_reason: 'open_invoice', recovery_status: null,
        active_recovery_attempt_id: null, d1_status: 'blocked', allowed_actions: ['view'],
        updated_at: '2026-08-15T10:30:00Z',
        available_methods: [
          { method: 'wallet', enabled: true, disabled_reason_code: null },
          { method: 'new_card', enabled: false, disabled_reason_code: 'rail_closed' },
          {
            method: 'saved_card', enabled: true, disabled_reason_code: null,
            saved_payment_method_ref: { id: 'pm-1', brand: 'visa', last_four: '6260', is_default: true },
          },
        ],
        active_recovery_attempt: null,
        timeline: [],
        financial_eligibility: {
          status: 'blocked', reason_codes: ['open_invoice'],
          evaluated_at: '2026-08-15T10:30:00Z', version: 1,
        },
        support_case_refs: [],
      },
    });

    await expect(getUnpaidInvoice('invoice-1')).resolves.toMatchObject({
      available_methods: [
        { method: 'wallet', enabled: true },
        { method: 'new_card', enabled: false, disabled_reason_code: 'rail_closed' },
        { method: 'saved_card', saved_payment_method_ref: { id: 'pm-1', last_four: '6260' } },
      ],
    });
  });

  it('maps CF-201 domain states and fails closed for future values', () => {
    expect(normalizeRecoveryStatus('provider_approved')).toBe('approved');
    expect(normalizeRecoveryStatus('duplicate_approved')).toBe('manual_review');
    expect(normalizeRecoveryStatus('provider_pending_v2')).toBe('unknown');
    expect(normalizeAllocationStatus('committed')).toBe('confirmed');
    expect(normalizeAllocationStatus('needs_review')).toBe('unknown');
    expect(normalizeEligibilityStatus('recheck_required')).toBe('evaluating');
    expect(normalizeEligibilityStatus('rail_closed')).toBe('unknown');
  });

  it('does not turn a duplicate approval into a second allocation', () => {
    const projection = normalizeRecoveryAttempt({
      attempt_id: 'attempt-2',
      invoice_id: 'invoice-1',
      status: 'duplicate_approved',
      reason_code: 'duplicate_approval',
      allocation: { status: 'committed', amount: '100.00', confirmed_at: '2026-08-13T12:00:00Z' },
      target_amount: '100.00',
      currency: 'COP',
      method: 'wallet',
      payment_order_id: null,
      next_action: { type: 'contact_support' },
      support_reference: 'support-1',
      allowed_actions: ['refresh'],
      version: 1,
      created_at: '2026-08-13T12:00:00Z',
      updated_at: '2026-08-13T12:00:00Z',
      financial_eligibility: {
        status: 'blocked', reason_codes: ['funds_unknown'],
        evaluated_at: '2026-08-13T12:00:00Z', version: 1,
      },
    });

    expect(projection.status).toBe('manual_review');
    expect(projection.reason_code).toBe('duplicate_approval');
    expect(projection.allocation).toBeNull();
  });

  it('keeps approved distinct from allocated and eligible', () => {
    const projection = normalizeRecoveryAttempt({
      attempt_id: 'attempt-1',
      invoice_id: 'invoice-1',
      target_amount: '100.00',
      status: 'provider_approved',
      currency: 'COP',
      method: 'wallet',
      payment_order_id: null,
      allocation: { status: 'pending', amount: '0.00', confirmed_at: null },
      financial_eligibility: {
        status: 'recheck_required', reason_codes: ['recovery_processing'],
        evaluated_at: '2026-08-13T12:00:00Z', version: 1,
      },
      next_action: { type: 'poll', poll_after_seconds: 5 },
      support_reference: 'support-1',
      allowed_actions: ['refresh'],
      version: 1,
      created_at: '2026-08-13T12:00:00Z',
      updated_at: '2026-08-13T12:00:00Z',
    });
    expect(projection.status).toBe('approved');
    expect(recoveryProjectionViewState(projection)).toBe('processing');
  });

  it('rejects numeric P002 decimal projections rather than coercing them', () => {
    expect(() => normalizeFinancialEligibility({
      status: 'eligible', reason_codes: [], evaluated_at: '2026-08-13T12:00:00Z', version: 1,
    })).not.toThrow();
    expect(() => normalizeFinancialEligibility({
      status: 'blocked', reason_codes: ['rail_closed'], evaluated_at: '2026-08-13T12:00:00Z', version: 1,
    })).toThrow(PayMp002Error);
    expect(() => normalizeRecoveryAttempt({
      status: 'allocated',
      target_amount: 100,
      allocation: { status: 'committed', amount: '100.00' },
      financial_eligibility: { status: 'eligible', reason_codes: [] },
    })).toThrow(PayMp002Error);
  });

  it('allows same-origin or explicit HTTPS hosts and rejects unsafe URLs', () => {
    const options = { sameOrigin: 'https://app.eslatin.com.co', allowedHosts: ['www.mercadopago.com'] } as const;
    expect(isAllowedHostedUrl('/checkout/opaque', options)).toBe(true);
    expect(isAllowedHostedUrl('https://www.mercadopago.com/checkout', options)).toBe(true);
    expect(isAllowedHostedUrl('javascript:alert(1)', options)).toBe(false);
    expect(isAllowedHostedUrl('https://evil.example/checkout', options)).toBe(false);
  });

  it('does not convert a failed response into an empty success page', async () => {
    mockedClient.get.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 503,
        data: { error: { code: 'PROVIDER_UNAVAILABLE', reference: 'ref-1', retryable: true } },
      },
    });
    await expect(getP002Transactions()).rejects.toMatchObject({
      canonical: expect.objectContaining({ code: 'PROVIDER_UNAVAILABLE', reference: 'ref-1', retryable: true }),
    });
  });
});
