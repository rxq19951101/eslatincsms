/**
 * 充电站状态管理 Slice
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { getChargers, getChargerById, getNearbyChargers, Charger, ChargerDetail, ChargersListParams } from '../../api/chargers';

export interface ChargerState {
  chargers: Charger[];
  selectedCharger: ChargerDetail | null;
  loading: boolean;
  error: string | null;
  lastFetch: number | null;
  filters: ChargersListParams;
}

const initialState: ChargerState = {
  chargers: [],
  selectedCharger: null,
  loading: false,
  error: null,
  lastFetch: null,
  filters: {},
};

/**
 * 获取充电站列表
 */
export const fetchChargers = createAsyncThunk(
  'charger/fetchChargers',
  async (params?: ChargersListParams, { rejectWithValue }) => {
    try {
      const data = await getChargers(params);
      return data;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch chargers');
    }
  }
);

/**
 * 获取附近的充电站
 */
export const fetchNearbyChargers = createAsyncThunk(
  'charger/fetchNearbyChargers',
  async (
    { latitude, longitude, radius }: { latitude: number; longitude: number; radius?: number },
    { rejectWithValue }
  ) => {
    try {
      const data = await getNearbyChargers(latitude, longitude, radius);
      return data;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch nearby chargers');
    }
  }
);

/**
 * 获取充电站详情
 */
export const fetchChargerById = createAsyncThunk(
  'charger/fetchChargerById',
  async (id: string, { rejectWithValue }) => {
    try {
      const data = await getChargerById(id);
      return data;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch charger details');
    }
  }
);

const chargerSlice = createSlice({
  name: 'charger',
  initialState,
  reducers: {
    setSelectedCharger: (state, action: PayloadAction<ChargerDetail | null>) => {
      state.selectedCharger = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
    setFilters: (state, action: PayloadAction<ChargersListParams>) => {
      state.filters = action.payload;
    },
    clearChargers: (state) => {
      state.chargers = [];
      state.lastFetch = null;
    },
  },
  extraReducers: (builder) => {
    // fetchChargers
    builder
      .addCase(fetchChargers.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchChargers.fulfilled, (state, action) => {
        state.loading = false;
        state.chargers = action.payload;
        state.lastFetch = Date.now();
        state.error = null;
      })
      .addCase(fetchChargers.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });

    // fetchNearbyChargers
    builder
      .addCase(fetchNearbyChargers.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchNearbyChargers.fulfilled, (state, action) => {
        state.loading = false;
        state.chargers = action.payload;
        state.lastFetch = Date.now();
        state.error = null;
      })
      .addCase(fetchNearbyChargers.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });

    // fetchChargerById
    builder
      .addCase(fetchChargerById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchChargerById.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedCharger = action.payload;
        state.error = null;
      })
      .addCase(fetchChargerById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { setSelectedCharger, clearError, setFilters, clearChargers } = chargerSlice.actions;

export default chargerSlice.reducer;
