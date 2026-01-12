/**
 * 扫码充电 Slice（start/active/stop）
 */

import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { ActiveChargingSession, MeterValuePoint, RemoteResponse } from '../../api/charging';
import { getActiveChargingSession, getMeterValues, startChargingByScan, stopCharging } from '../../api/charging';

export interface ChargingState {
  chargePointId: string | null;
  connectorId: number | null;
  activeSession: ActiveChargingSession | null;
  lastStoppedSession: ActiveChargingSession | null;
  meterValues: MeterValuePoint[];
  lastMeterId: number | null;
  loadingMeter: boolean;
  meterError: string | null;
  starting: boolean;
  stopping: boolean;
  loadingActive: boolean;
  error: string | null;
  lastRemoteResult: RemoteResponse | null;
}

const initialState: ChargingState = {
  chargePointId: null,
  connectorId: null,
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
};

export const startCharging = createAsyncThunk(
  'charging/start',
  async (
    { chargePointId, connectorId }: { chargePointId: string; connectorId: number },
    { rejectWithValue }
  ) => {
    try {
      const res = await startChargingByScan({ chargePointId, connectorId });
      return { chargePointId, connectorId, res };
    } catch (e: any) {
      const msg =
        e?.response?.data?.detail ||
        e?.response?.data?.message ||
        e?.message ||
        'Failed to start charging';
      return rejectWithValue(msg);
    }
  }
);

export const fetchActiveSession = createAsyncThunk(
  'charging/fetchActive',
  async (chargePointId: string, { rejectWithValue }) => {
    try {
      const session = await getActiveChargingSession(chargePointId);
      return { chargePointId, session };
    } catch (e: any) {
      const msg =
        e?.response?.data?.detail ||
        e?.response?.data?.message ||
        e?.message ||
        'Failed to fetch active session';
      return rejectWithValue(msg);
    }
  }
);

export const fetchMeterValuePoints = createAsyncThunk(
  'charging/fetchMeterValues',
  async (
    { sessionId, sinceId }: { sessionId: number; sinceId?: number },
    { rejectWithValue }
  ) => {
    try {
      const points = await getMeterValues({ sessionId, sinceId, limit: 50 });
      return { sessionId, points };
    } catch (e: any) {
      const msg =
        e?.response?.data?.detail ||
        e?.response?.data?.message ||
        e?.message ||
        'Failed to fetch meter values';
      return rejectWithValue(msg);
    }
  }
);

export const stopChargingSession = createAsyncThunk(
  'charging/stop',
  async (chargePointId: string, { rejectWithValue }) => {
    try {
      const res = await stopCharging(chargePointId);
      return { chargePointId, res };
    } catch (e: any) {
      const msg =
        e?.response?.data?.detail ||
        e?.response?.data?.message ||
        e?.message ||
        'Failed to stop charging';
      return rejectWithValue(msg);
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
    resetChargingState: () => initialState,
    setChargingTarget: (
      state,
      action: PayloadAction<{ chargePointId: string; connectorId: number }>
    ) => {
      state.chargePointId = action.payload.chargePointId;
      state.connectorId = action.payload.connectorId;
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
        state.chargePointId = action.payload.chargePointId;
        state.connectorId = action.payload.connectorId;
        state.lastRemoteResult = action.payload.res;
      })
      .addCase(startCharging.rejected, (state, action) => {
        state.starting = false;
        state.error = action.payload as string;
      })
      // fetchActive
      .addCase(fetchActiveSession.pending, (state) => {
        state.loadingActive = true;
        state.error = null;
      })
      .addCase(fetchActiveSession.fulfilled, (state, action) => {
        state.loadingActive = false;
        state.chargePointId = action.payload.chargePointId;
        state.activeSession = action.payload.session;
        // session 变化时清空 meterValues（避免把旧会话的数据展示出来）
        if (!action.payload.session) {
          state.meterValues = [];
          state.lastMeterId = null;
        }
      })
      .addCase(fetchActiveSession.rejected, (state, action) => {
        state.loadingActive = false;
        state.error = action.payload as string;
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
          // 追加（去重：基于 id）
          const existingIds = new Set(state.meterValues.map((p) => p.id));
          for (const p of newPoints) {
            if (!existingIds.has(p.id)) state.meterValues.push(p);
          }
          // 更新 lastMeterId
          state.lastMeterId = state.meterValues.reduce((m, p) => (p.id > m ? p.id : m), state.lastMeterId || 0);
          // 控制内存：只保留最近 300 条
          if (state.meterValues.length > 300) {
            state.meterValues = state.meterValues.slice(state.meterValues.length - 300);
          }
        }
      })
      .addCase(fetchMeterValuePoints.rejected, (state, action) => {
        state.loadingMeter = false;
        state.meterError = action.payload as string;
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
        if (state.activeSession?.charge_point_id === action.payload.chargePointId) {
          state.lastStoppedSession = state.activeSession;
        }
      })
      .addCase(stopChargingSession.rejected, (state, action) => {
        state.stopping = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearChargingError, resetChargingState, setChargingTarget } = chargingSlice.actions;
export default chargingSlice.reducer;

