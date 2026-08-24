import { configureStore } from '@reduxjs/toolkit';
import chargingReducer, {
  fetchActiveSession,
  fetchMeterValuePoints,
  restoreActiveSession,
  startCharging,
} from '../chargingSlice';
import { getActiveChargingSession, getMeterValues, startChargingByScan } from '../../../api/charging';

jest.mock('../../../api/charging', () => ({
  getActiveChargingSession: jest.fn(),
  getMeterValues: jest.fn(),
  startChargingByScan: jest.fn(),
  stopCharging: jest.fn(),
}));

jest.mock('../../../api/client', () => ({
  handleApiError: jest.fn(() => ({ code: 'UNKNOWN', status: 500 })),
}));

const mockedStart = startChargingByScan as jest.MockedFunction<typeof startChargingByScan>;
const mockedActive = getActiveChargingSession as jest.MockedFunction<typeof getActiveChargingSession>;
const mockedMeter = getMeterValues as jest.MockedFunction<typeof getMeterValues>;

function createStore() {
  return configureStore({ reducer: { charging: chargingReducer } });
}

describe('charging request safety', () => {
  beforeEach(() => jest.clearAllMocks());

  it('allows only one start request while the first click is in flight', async () => {
    let resolveStart: ((value: { success: boolean; result: 'accepted' }) => void) | undefined;
    mockedStart.mockImplementation(() => new Promise((resolve) => {
      resolveStart = resolve;
    }));
    const store = createStore();

    const first = store.dispatch(startCharging({ qrToken: 'public-qr' }));
    const duplicate = store.dispatch(startCharging({ qrToken: 'public-qr' }));

    expect(mockedStart).toHaveBeenCalledTimes(1);
    resolveStart?.({ success: true, result: 'accepted' });
    await first;
    await duplicate;
    expect(mockedStart).toHaveBeenCalledTimes(1);
  });

  it('restores an ongoing session with a read-only lookup', async () => {
    mockedActive.mockResolvedValueOnce({
      id: 'session-uuid',
      transaction_id: 7,
      charge_point_id: 'internal-charge-point-uuid',
      ocpp_identity: 'CP-PUBLIC-7',
      evse_id: 'evse-uuid',
      id_tag: 'APP-user',
      start_time: '2026-07-18T12:00:00Z',
      end_time: null,
      status: 'ongoing',
      meter_start: 0,
      meter_stop: null,
    });
    const store = createStore();

    await store.dispatch(restoreActiveSession());

    expect(mockedActive).toHaveBeenCalledWith();
    expect(mockedStart).not.toHaveBeenCalled();
    expect(store.getState().charging).toMatchObject({
      recoveryChecked: true,
      qrToken: null,
      activeSession: { ocpp_identity: 'CP-PUBLIC-7' },
    });
  });

  it('does not overlap active-session lookups', async () => {
    let resolveActive: ((value: null) => void) | undefined;
    mockedActive.mockImplementation(() => new Promise((resolve) => {
      resolveActive = resolve;
    }));
    const store = createStore();

    const first = store.dispatch(fetchActiveSession(undefined));
    const duplicate = store.dispatch(fetchActiveSession(undefined));

    expect(mockedActive).toHaveBeenCalledTimes(1);
    resolveActive?.(null);
    await first;
    await duplicate;
    expect(mockedActive).toHaveBeenCalledTimes(1);
  });

  it('does not overlap meter-value lookups', async () => {
    let resolveMeter: ((value: []) => void) | undefined;
    mockedMeter.mockImplementation(() => new Promise((resolve) => {
      resolveMeter = resolve;
    }));
    const store = createStore();

    const first = store.dispatch(fetchMeterValuePoints({ sessionId: 'session-1' }));
    const duplicate = store.dispatch(fetchMeterValuePoints({ sessionId: 'session-1' }));

    expect(mockedMeter).toHaveBeenCalledTimes(1);
    resolveMeter?.([]);
    await first;
    await duplicate;
    expect(mockedMeter).toHaveBeenCalledTimes(1);
  });

  it('replaces realtime meter snapshots without using them as the database cursor', async () => {
    mockedMeter
      .mockResolvedValueOnce([
        {
          id: '44444444-4444-4444-8444-444444444444',
          source: 'database',
          timestamp: '2026-01-01T00:00:00Z',
          connector_id: 1,
          value_wh: 100,
          energy_kwh: 0.1,
          power_kw: 7,
          current_a: 32,
          voltage_v: 220,
          soc: 20,
        },
        {
          id: 'realtime:2026-01-01T00:00:05Z',
          source: 'realtime',
          timestamp: '2026-01-01T00:00:05Z',
          connector_id: 1,
          value_wh: 110,
          energy_kwh: 0.11,
          power_kw: 7,
          current_a: 32,
          voltage_v: 220,
          soc: 21,
        },
      ])
      .mockResolvedValueOnce([
        {
          id: 'realtime:2026-01-01T00:00:10Z',
          source: 'realtime',
          timestamp: '2026-01-01T00:00:10Z',
          connector_id: 1,
          value_wh: 120,
          energy_kwh: 0.12,
          power_kw: 7,
          current_a: 32,
          voltage_v: 220,
          soc: 22,
        },
      ]);
    const store = createStore();

    await store.dispatch(fetchMeterValuePoints({ sessionId: 'session-1' }));
    await store.dispatch(fetchMeterValuePoints({ sessionId: 'session-1' }));

    const state = store.getState().charging;
    expect(state.lastMeterId).toBe('44444444-4444-4444-8444-444444444444');
    expect(state.meterValues.filter((point) => point.source === 'realtime')).toHaveLength(1);
    expect(state.meterValues[state.meterValues.length - 1].value_wh).toBe(120);
  });

  it('keeps the last active session and normal error state when foreground recovery fails', async () => {
    mockedActive.mockRejectedValueOnce(new Error('temporary network failure'));
    const previousState = chargingReducer(undefined, { type: 'init' });
    const activeSession = {
      id: 'session-kept',
      transaction_id: 8,
      charge_point_id: 'internal-id',
      ocpp_identity: 'CP-PUBLIC-8',
      evse_id: '1',
      id_tag: 'APP-user',
      start_time: '2026-07-18T12:00:00Z',
      end_time: null,
      status: 'ongoing',
      meter_start: 0,
      meter_stop: null,
    };
    const store = configureStore({
      reducer: { charging: chargingReducer },
      preloadedState: {
        charging: {
          ...previousState,
          activeSession,
          error: { operation: 'start' as const, code: 'START_FAILED', status: 409 },
        },
      },
    });

    await store.dispatch(restoreActiveSession());

    expect(store.getState().charging).toMatchObject({
      recoveryChecked: true,
      recovering: false,
      activeSession: { id: 'session-kept' },
      error: { operation: 'start', code: 'START_FAILED', status: 409 },
    });
  });
});
