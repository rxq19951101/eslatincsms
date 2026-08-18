/**
 * 扫码充电 Slice（start/active/stop）
 */

import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import type {
  ActiveChargingSession,
  ChargingSettlementMethod,
  MeterValuePoint,
  RemoteResponse,
} from '../../api/charging';
import { getActiveChargingSession, getMeterValues, startChargingByScan, stopCharging } from '../../api/charging';
import { handleApiError } from '../../api/client';

export type ChargingOperation = 'start' | 'active' | 'restore' | 'meter' | 'stop';

export interface ChargingFailure {
  operation: ChargingOperation;
  code?: string;
  status?: number;
}

export interface ChargingState {
  qrToken: string | null;
  activeSession: ActiveChargingSession | null;
  lastStoppedSession: ActiveChargingSession | null;
  meterValues: MeterValuePoint[];
  lastMeterId: string | null;
  loadingMeter: boolean;
  meterError: ChargingFailure | null;
  starting: boolean;
  stopping: boolean;
  loadingActive: boolean;
  error: ChargingFailure | null;
  lastRemoteResult: RemoteResponse | null;
  recoveryChecked: boolean;
  recovering: boolean;
  settlementMethod: ChargingSettlementMethod | 'free' | null;
  paymentIntentId: string | null;
}

const initialState: ChargingState = {
  qrToken: null,
  activeSession: null,
  lastStoppedSession: null,
  meterValues: [],
  lastMeterId: null,
  loadingMeter: false,
  meterError: null,
  starting: false,
  stopping: false,
  loadingActive: false,
  error: null,
  lastRemoteResult: null,
  recoveryChecked: false,
  recovering: false,
  settlementMethod: null,
  paymentIntentId: null,
};

function chargingFailure(error: unknown, operation: ChargingOperation): ChargingFailure {
  const parsed = handleApiError(error);
  return { operation, code: parsed.code, status: parsed.status };
}

export const startCharging = createAsyncThunk(
  'charging/start',
  async (
    {
      qrToken,
      settlementMethod,
      paymentIntentId,
    }: {
      qrToken: string;
      settlementMethod?: ChargingSettlementMethod;
      paymentIntentId?: string | null;
    },
    { rejectWithValue }
  ) => {
    try {
      const res = await startChargingByScan({
        qrToken,
        ...(settlementMethod ? { settlementMethod } : {}),
        ...(paymentIntentId ? { paymentIntentId } : {}),
      });
      return { qrToken, res, settlementMethod: settlementMethod ?? 'wallet', paymentIntentId: paymentIntentId ?? null };
    } catch (e: unknown) {
      return rejectWithValue(chargingFailure(e, 'start'));
    }
  },
  {
    condition: (_, { getState }) => {
      const state = getState() as { charging: ChargingState };
      return !state.charging.starting;
    },
  }
);

export const fetchActiveSession = createAsyncThunk(
  'charging/fetchActive',
  async (qrToken: string | undefined, { rejectWithValue }) => {
    try {
      const session = await getActiveChargingSession(qrToken);
      return { qrToken, session };
    } catch (e: unknown) {
      return rejectWithValue(chargingFailure(e, 'active'));
    }
  },
  {
    condition: (_, { getState }) => {
      const state = getState() as { charging: ChargingState };
      return !state.charging.loadingActive && !state.charging.recovering;
    },
  }
);

/** One read-only lookup after startup/login; this thunk never sends start. */
export const restoreActiveSession = createAsyncThunk(
  'charging/restoreActive',
  async (_, { rejectWithValue }) => {
    try {
      return await getActiveChargingSession();
    } catch (e: unknown) {
      return rejectWithValue(chargingFailure(e, 'restore'));
    }
  },
  {
    condition: (_, { getState }) => {
      const state = getState() as { charging: ChargingState };
      return !state.charging.recovering && !state.charging.loadingActive;
    },
  }
);

export const fetchMeterValuePoints = createAsyncThunk(
  'charging/fetchMeterValues',
  async (
    { sessionId, sinceId }: { sessionId: string; sinceId?: string },
    { rejectWithValue }
  ) => {
    try {
      const points = await getMeterValues({ sessionId, sinceId, limit: 50 });
      return { sessionId, points };
    } catch (e: unknown) {
      return rejectWithValue(chargingFailure(e, 'meter'));
    }
  },
  {
    condition: (_, { getState }) => {
      const state = getState() as { charging: ChargingState };
      return !state.charging.loadingMeter;
    },
  }
);

export const stopChargingSession = createAsyncThunk(
  'charging/stop',
  async (sessionId: string, { rejectWithValue }) => {
    try {
      const res = await stopCharging(sessionId);
      return { sessionId, res };
    } catch (e: unknown) {
      return rejectWithValue(chargingFailure(e, 'stop'));
    }
  }
);

const chargingSlice = createSlice({
  name: 'charging',
  initialState,
  reducers: {
    clearChargingError: (state) => {
      state.error = null;
    },
    clearChargingTarget: (state) => {
      state.qrToken = null;
    },
    resetChargingState: () => initialState,
    setChargingTarget: (state, action: PayloadAction<{ qrToken: string }>) => {
      state.qrToken = action.payload.qrToken;
    },
  },
  extraReducers: (builder) => {
    builder
      // start
      .addCase(startCharging.pending, (state) => {
        state.starting = true;
        state.error = null;
      })
      .addCase(startCharging.fulfilled, (state, action) => {
        state.starting = false;
        state.qrToken = action.payload.qrToken;
        state.lastRemoteResult = action.payload.res;
        state.settlementMethod = action.payload.settlementMethod;
        state.paymentIntentId = action.payload.paymentIntentId;
        if (action.payload.res.session) {
          state.activeSession = action.payload.res.session;
        }
      })
      .addCase(startCharging.rejected, (state, action) => {
        state.starting = false;
        if (action.payload) state.error = action.payload as ChargingFailure;
      })
      // fetchActive
      .addCase(fetchActiveSession.pending, (state) => {
        state.loadingActive = true;
        state.error = null;
      })
      .addCase(fetchActiveSession.fulfilled, (state, action) => {
        state.loadingActive = false;
        state.qrToken = action.payload.qrToken ?? null;
        state.activeSession = action.payload.session;
        // session 变化时清空 meterValues（避免把旧会话的数据展示出来）
        if (!action.payload.session) {
          state.meterValues = [];
          state.lastMeterId = null;
        }
      })
      .addCase(fetchActiveSession.rejected, (state, action) => {
        state.loadingActive = false;
        if (action.payload) state.error = action.payload as ChargingFailure;
      })
      // startup/login recovery (GET only)
      .addCase(restoreActiveSession.pending, (state) => {
        state.recovering = true;
        state.recoveryChecked = false;
      })
      .addCase(restoreActiveSession.fulfilled, (state, action) => {
        state.recovering = false;
        state.recoveryChecked = true;
        state.activeSession = action.payload;
        state.qrToken = null;
      })
      .addCase(restoreActiveSession.rejected, (state) => {
        state.recovering = false;
        state.recoveryChecked = true;
        // Recovery is best-effort: preserve the last known active entry and normal screen errors.
      })
      // meter values
      .addCase(fetchMeterValuePoints.pending, (state) => {
        state.loadingMeter = true;
        state.meterError = null;
      })
      .addCase(fetchMeterValuePoints.fulfilled, (state, action) => {
        state.loadingMeter = false;
        const newPoints = action.payload.points || [];
        if (newPoints.length > 0) {
          // Redis 只保留最新实时快照，新的实时点替换旧实时点。
          if (newPoints.some((p) => p.source === 'realtime')) {
            state.meterValues = state.meterValues.filter((p) => p.source !== 'realtime');
          }
          // 追加（去重：基于 id）
          const existingIds = new Set(state.meterValues.map((p) => p.id));
          for (const p of newPoints) {
            if (!existingIds.has(p.id)) state.meterValues.push(p);
          }
          // Redis 实时 ID 不能作为数据库 since_id；游标只跟随持久化记录。
          const persistedPoints = newPoints.filter((p) => p.source !== 'realtime');
          if (persistedPoints.length > 0) {
            state.lastMeterId = persistedPoints[persistedPoints.length - 1].id;
          }
          // 控制内存：只保留最近 300 条
          if (state.meterValues.length > 300) {
            state.meterValues = state.meterValues.slice(state.meterValues.length - 300);
          }
        }
      })
      .addCase(fetchMeterValuePoints.rejected, (state, action) => {
        state.loadingMeter = false;
        if (action.payload) state.meterError = action.payload as ChargingFailure;
      })
      // stop
      .addCase(stopChargingSession.pending, (state) => {
        state.stopping = true;
        state.error = null;
      })
      .addCase(stopChargingSession.fulfilled, (state, action) => {
        state.stopping = false;
        state.lastRemoteResult = action.payload.res;
        // stop 只是“请求已发送”，本地先把 activeSession 备份；真正结束靠轮询 /active 变成 null
        if (state.activeSession?.id === action.payload.sessionId) {
          state.lastStoppedSession = state.activeSession;
        }
      })
      .addCase(stopChargingSession.rejected, (state, action) => {
        state.stopping = false;
        if (action.payload) state.error = action.payload as ChargingFailure;
      });
  },
});

export const { clearChargingError, resetChargingState, setChargingTarget } = chargingSlice.actions;
export default chargingSlice.reducer;
