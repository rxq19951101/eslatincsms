import apiClient from '../../../api/client';
import { getP002Transactions, normalizeRecoveryAttempt } from '../adapter';

jest.mock('../../../api/client', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('FE-201 QA runtime boundary evidence', () => {
  beforeEach(() => jest.clearAllMocks());

  it('rejects a projection missing required RecoveryAttempt fields', () => {
    expect(() => normalizeRecoveryAttempt({
      status: 'processing',
      allocation: null,
      financial_eligibility: {
        status: 'unknown', reason_codes: [], evaluated_at: '2026-08-13T12:00:00Z', version: 1,
      },
    })).toThrow();
  });

  it('does not retain forbidden sensitive fields from an untrusted projection', () => {
    const projection = normalizeRecoveryAttempt({
      attempt_id: 'attempt-1',
      invoice_id: 'invoice-1',
      target_amount: '100.00',
      currency: 'COP',
      method: 'wallet',
      status: 'processing',
      allocation: null,
      financial_eligibility: {
        status: 'unknown', reason_codes: [], evaluated_at: '2026-08-13T12:00:00Z', version: 1,
      },
      next_action: { type: 'poll', poll_after_seconds: 5 },
      support_reference: 'support-1',
      allowed_actions: ['refresh'],
      payment_order_id: null,
      version: 1,
      created_at: '2026-08-13T12:00:00Z',
      updated_at: '2026-08-13T12:00:00Z',
      pan: '4111111111111111',
      cvv: '123',
      raw_provider_payload: { token: 'provider-secret' },
    });

    expect(projection).not.toHaveProperty('pan');
    expect(projection).not.toHaveProperty('cvv');
    expect(projection).not.toHaveProperty('raw_provider_payload');
  });

  it('rebuilds P002 transactions from the frozen allowlist', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        items: [{
          id: 'session-1',
          transaction_id: 42,
          charge_point_id: 'charger-1',
          ocpp_identity: 'CP-1',
          evse_id: 'evse-1',
          start_time: '2026-08-13T12:00:00Z',
          end_time: null,
          status: 'charging',
          energy_kwh: '6.800',
          duration_minutes: '30.000',
          site_name: 'Station',
          site_address: 'Address',
          unknown_field: 'must-not-cross-boundary',
          pan: '4111111111111111',
          cvv: '123',
          raw_provider_payload: { token: 'provider-secret' },
        }],
        page: { next_cursor: null, has_more: false },
      },
    });

    const result = await getP002Transactions({ cursor: 'cursor-1', limit: 1 });

    expect(result.items[0]).toEqual({
      id: 'session-1',
      transaction_id: 42,
      charge_point_id: 'charger-1',
      ocpp_identity: 'CP-1',
      evse_id: 'evse-1',
      start_time: '2026-08-13T12:00:00Z',
      end_time: null,
      status: 'charging',
      energy_kwh: '6.800',
      duration_minutes: '30.000',
      site_name: 'Station',
      site_address: 'Address',
    });
    expect(result.items[0]).not.toHaveProperty('unknown_field');
    expect(result.items[0]).not.toHaveProperty('pan');
    expect(result.items[0]).not.toHaveProperty('cvv');
    expect(result.items[0]).not.toHaveProperty('raw_provider_payload');
  });

  it('rejects malformed or incomplete P002 transaction fields fail closed', async () => {
    const validTransaction: Record<string, unknown> = {
      id: 'session-1',
      transaction_id: 42,
      charge_point_id: 'charger-1',
      ocpp_identity: 'CP-1',
      evse_id: 'evse-1',
      start_time: '2026-08-13T12:00:00Z',
      end_time: null,
      status: 'charging',
      energy_kwh: '6.800',
      duration_minutes: '30.000',
      site_name: 'Station',
      site_address: 'Address',
    };
    const expectInvalid = async (transaction: Record<string, unknown>) => {
      mockedClient.get.mockResolvedValueOnce({
        data: { items: [transaction], page: { next_cursor: null, has_more: false } },
      });
      await expect(getP002Transactions()).rejects.toMatchObject({
        canonical: expect.objectContaining({ code: 'RESPONSE_INVALID' }),
      });
    };

    const requiredFields = [
      'id', 'transaction_id', 'charge_point_id', 'ocpp_identity', 'evse_id',
      'start_time', 'end_time', 'status', 'energy_kwh', 'duration_minutes',
      'site_name', 'site_address',
    ];
    for (const field of requiredFields) {
      const transaction = { ...validTransaction };
      delete transaction[field];
      await expectInvalid(transaction);
    }

    const invalidValues: Array<[string, unknown]> = [
      ['id', {}],
      ['transaction_id', '42'],
      ['charge_point_id', {}],
      ['ocpp_identity', 42],
      ['evse_id', null],
      ['start_time', 123],
      ['end_time', '2026-08-13T12:00:00-05:00'],
      ['status', {}],
      ['energy_kwh', 6.8],
      ['duration_minutes', {}],
      ['site_name', 42],
      ['site_address', {}],
    ];
    for (const [field, invalidValue] of invalidValues) {
      await expectInvalid({ ...validTransaction, [field]: invalidValue });
    }
  });
});
