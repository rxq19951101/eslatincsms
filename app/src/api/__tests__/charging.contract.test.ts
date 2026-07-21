import apiClient from '../client';
import { getActiveChargingSession, getMeterValues, settleCharging, startChargingByScan, stopCharging } from '../charging';
import { getChargingRecordDetail } from '../transactions';

jest.mock('../client', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
  handleApiError: jest.fn(),
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('App charging UUID contract', () => {
  beforeEach(() => jest.clearAllMocks());

  it('keeps session/EVSE/meter IDs as UUID strings and OCPP IDs as numbers', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        id: '11111111-1111-4111-8111-111111111111',
        transaction_id: 731,
        charge_point_id: '22222222-2222-4222-8222-222222222222',
        evse_id: '33333333-3333-4333-8333-333333333333',
        id_tag: 'APPUSER:user',
        start_time: '2026-07-18T12:00:00Z',
        end_time: null,
        status: 'ongoing',
        meter_start: 1000,
        meter_stop: null,
      },
    });

    const session = await getActiveChargingSession('public-qr-token');
    expect(session).toMatchObject({
      id: '11111111-1111-4111-8111-111111111111',
      evse_id: '33333333-3333-4333-8333-333333333333',
      transaction_id: 731,
    });
    expect(typeof session?.id).toBe('string');
    expect(typeof session?.evse_id).toBe('string');
    expect(typeof session?.transaction_id).toBe('number');
  });

  it('sends UUID session and meter cursor values without numeric coercion', async () => {
    mockedClient.get.mockResolvedValueOnce({ data: [{
      id: '44444444-4444-4444-8444-444444444444',
      timestamp: '2026-07-18T12:01:00Z',
      connector_id: 1,
      value_wh: 1200,
      energy_kwh: 1.2,
      power_kw: 7.2,
      current_a: 32,
      voltage_v: 225,
      soc: 50,
    }] });
    const sessionId = '11111111-1111-4111-8111-111111111111';
    const sinceId = '33333333-3333-4333-8333-333333333333';
    const points = await getMeterValues({ sessionId, sinceId });

    expect(mockedClient.get).toHaveBeenCalledWith(expect.any(String), {
      params: { session_id: sessionId, since_id: sinceId, limit: 50 },
    });
    expect(points[0].id).toBe('44444444-4444-4444-8444-444444444444');
    expect(points[0].connector_id).toBe(1);
  });

  it('discovers the signed-in user session without a QR token and never starts charging', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: {
        id: '11111111-1111-4111-8111-111111111111',
        transaction_id: 731,
        charge_point_id: '22222222-2222-4222-8222-222222222222',
        ocpp_identity: 'SIM-E2E-CP-001',
        evse_id: '33333333-3333-4333-8333-333333333333',
        id_tag: 'APPUSER:user',
        start_time: '2026-07-18T12:00:00Z',
        end_time: null,
        status: 'ongoing',
        meter_start: 1000,
        meter_stop: null,
      },
    });

    const session = await getActiveChargingSession();

    expect(mockedClient.get).toHaveBeenCalledWith(expect.any(String));
    expect(mockedClient.post).not.toHaveBeenCalled();
    expect(session).toMatchObject({
      ocpp_identity: 'SIM-E2E-CP-001',
    });
    expect(session).not.toHaveProperty('qr_token');
  });

  it('normalizes the already_active public session returned by start', async () => {
    mockedClient.post.mockResolvedValueOnce({
      data: {
        success: true,
        status: 'already_active',
        session: {
          session_id: '11111111-1111-4111-8111-111111111111',
          transaction_id: 731,
          charge_point_id: '22222222-2222-4222-8222-222222222222',
          ocpp_identity: 'SIM-E2E-CP-001',
          connector_id: 1,
          status: 'ongoing',
          start_time: '2026-07-18T12:00:00Z',
          meter_start: 1000,
          meter_stop: null,
        },
      },
    });

    const result = await startChargingByScan({ qrToken: 'public-qr-token' });

    expect(result.session).toMatchObject({
      id: '11111111-1111-4111-8111-111111111111',
      ocpp_identity: 'SIM-E2E-CP-001',
    });
    expect(result.session).not.toHaveProperty('qr_token');
  });

  it('stops a recovered session by session ID without a QR token', async () => {
    const sessionId = '11111111-1111-4111-8111-111111111111';
    mockedClient.post.mockResolvedValueOnce({ data: { success: true } });

    await stopCharging(sessionId);

    expect(mockedClient.post).toHaveBeenCalledWith(expect.any(String), { session_id: sessionId });
  });

  it('uses UUID session IDs for settlement and history detail routes', async () => {
    const sessionId = '11111111-1111-4111-8111-111111111111';
    mockedClient.post.mockResolvedValueOnce({ data: { already_settled: false } });
    mockedClient.get.mockResolvedValueOnce({ data: { id: sessionId, transaction_id: 731 } });

    await settleCharging(sessionId);
    await getChargingRecordDetail(sessionId);

    expect(mockedClient.post).toHaveBeenCalledWith(expect.any(String), { session_id: sessionId });
    expect(mockedClient.get).toHaveBeenCalledWith(expect.stringContaining(sessionId));
  });
});
