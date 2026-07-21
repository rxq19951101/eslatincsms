import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';
import {
  getSiteById,
  getSites,
  type SiteDetail,
  type SiteSummary,
  type SitesListParams,
} from '../../api/sites';

interface SiteState {
  sites: SiteSummary[];
  selectedSite: SiteDetail | null;
  loading: boolean;
  error: string | null;
}

const initialState: SiteState = {
  sites: [],
  selectedSite: null,
  loading: false,
  error: null,
};

export const fetchSites = createAsyncThunk(
  'site/fetchSites',
  async (params: SitesListParams | undefined, { rejectWithValue }) => {
    try {
      return await getSites(params);
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch sites');
    }
  }
);

export const fetchSiteById = createAsyncThunk(
  'site/fetchSiteById',
  async (id: string, { rejectWithValue }) => {
    try {
      return await getSiteById(id);
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch site details');
    }
  }
);

const siteSlice = createSlice({
  name: 'site',
  initialState,
  reducers: {
    setSelectedSite: (state, action: PayloadAction<SiteDetail | null>) => {
      state.selectedSite = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSites.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSites.fulfilled, (state, action) => {
        state.loading = false;
        state.sites = action.payload;
      })
      .addCase(fetchSites.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(fetchSiteById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSiteById.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedSite = action.payload;
      })
      .addCase(fetchSiteById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { setSelectedSite } = siteSlice.actions;
export default siteSlice.reducer;
