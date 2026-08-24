/**
 * 充电记录（订单记录）Slice
 */

import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { ChargingRecord, ChargingRecordDetail } from '../../api/transactions';
import { getChargingRecordDetail, getChargingRecords } from '../../api/transactions';
import { handleApiError } from '../../api/client';
import { getT } from '../../i18n';

export interface TransactionsState {
  items: ChargingRecord[];
  selected: ChargingRecordDetail | null;
  loadingList: boolean;
  loadingDetail: boolean;
  error: string | null;
}

const initialState: TransactionsState = {
  items: [],
  selected: null,
  loadingList: false,
  loadingDetail: false,
  error: null,
};

function extractErrorMessage(e: any, fallback: string) {
  return handleApiError(e).message || fallback;
}

export const fetchChargingRecords = createAsyncThunk(
  'transactions/fetchList',
  async (params: { status?: string; limit?: number; offset?: number } | undefined, { rejectWithValue }) => {
    try {
      return await getChargingRecords(params);
    } catch (e: any) {
      return rejectWithValue(extractErrorMessage(e, getT().history.loadFailed));
    }
  }
);

export const fetchChargingRecordDetail = createAsyncThunk(
  'transactions/fetchDetail',
  async (id: string, { rejectWithValue }) => {
    try {
      return await getChargingRecordDetail(id);
    } catch (e: any) {
      return rejectWithValue(extractErrorMessage(e, getT().history.loadFailed));
    }
  }
);

const transactionsSlice = createSlice({
  name: 'transactions',
  initialState,
  reducers: {
    clearTransactionsError: (state) => {
      state.error = null;
    },
    clearSelectedRecord: (state) => {
      state.selected = null;
    },
    setSelectedRecord: (state, action: PayloadAction<ChargingRecordDetail | null>) => {
      state.selected = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // list
      .addCase(fetchChargingRecords.pending, (state) => {
        state.loadingList = true;
        state.error = null;
      })
      .addCase(fetchChargingRecords.fulfilled, (state, action) => {
        state.loadingList = false;
        state.items = action.payload;
      })
      .addCase(fetchChargingRecords.rejected, (state, action) => {
        state.loadingList = false;
        state.error = action.payload as string;
      })
      // detail
      .addCase(fetchChargingRecordDetail.pending, (state) => {
        state.loadingDetail = true;
        state.error = null;
      })
      .addCase(fetchChargingRecordDetail.fulfilled, (state, action) => {
        state.loadingDetail = false;
        state.selected = action.payload;
      })
      .addCase(fetchChargingRecordDetail.rejected, (state, action) => {
        state.loadingDetail = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearTransactionsError, clearSelectedRecord, setSelectedRecord } = transactionsSlice.actions;
export default transactionsSlice.reducer;
