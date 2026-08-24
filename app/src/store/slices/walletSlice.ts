/**
 * 钱包 Slice（简化版）
 */

import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { CreateCheckoutSessionResponse, WalletBalance, WalletTransaction } from '../../types';
import { getWalletBalance, getWalletTransactions, topUpWallet } from '../../api/wallet';
import { handleApiError } from '../../api/client';
import { getT } from '../../i18n';

export interface WalletState {
  balance: WalletBalance | null;
  transactions: WalletTransaction[];
  loadingBalance: boolean;
  loadingTx: boolean;
  toppingUp: boolean;
  error: string | null;
}

const initialState: WalletState = {
  balance: null,
  transactions: [],
  loadingBalance: false,
  loadingTx: false,
  toppingUp: false,
  error: null,
};

function extractErrorMessage(e: any, fallback: string) {
  return handleApiError(e).message || fallback;
}

export const fetchWalletBalance = createAsyncThunk('wallet/fetchBalance', async (_, { rejectWithValue }) => {
  try {
    return await getWalletBalance();
  } catch (e: any) {
    return rejectWithValue(extractErrorMessage(e, getT().wallet.loadFailed));
  }
});

export const fetchWalletTransactions = createAsyncThunk(
  'wallet/fetchTransactions',
  async (params: { limit?: number; offset?: number } | undefined, { rejectWithValue }) => {
    try {
      return await getWalletTransactions(params);
    } catch (e: any) {
      return rejectWithValue(extractErrorMessage(e, getT().wallet.loadFailed));
    }
  }
);

export const topUp = createAsyncThunk('wallet/topUp', async (amount: number, { rejectWithValue }) => {
  try {
    return await topUpWallet(amount);
  } catch (e: any) {
    return rejectWithValue(extractErrorMessage(e, getT().payment.createFailed));
  }
});

const walletSlice = createSlice({
  name: 'wallet',
  initialState,
  reducers: {
    clearWalletError: (state) => {
      state.error = null;
    },
    setBalance: (state, action: PayloadAction<WalletBalance | null>) => {
      state.balance = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // balance
      .addCase(fetchWalletBalance.pending, (state) => {
        state.loadingBalance = true;
        state.error = null;
      })
      .addCase(fetchWalletBalance.fulfilled, (state, action) => {
        state.loadingBalance = false;
        state.balance = action.payload;
      })
      .addCase(fetchWalletBalance.rejected, (state, action) => {
        state.loadingBalance = false;
        state.error = action.payload as string;
      })
      // tx
      .addCase(fetchWalletTransactions.pending, (state) => {
        state.loadingTx = true;
        state.error = null;
      })
      .addCase(fetchWalletTransactions.fulfilled, (state, action) => {
        state.loadingTx = false;
        state.transactions = action.payload;
      })
      .addCase(fetchWalletTransactions.rejected, (state, action) => {
        state.loadingTx = false;
        state.error = action.payload as string;
      })
      // top up
      .addCase(topUp.pending, (state) => {
        state.toppingUp = true;
        state.error = null;
      })
      .addCase(topUp.fulfilled, (state, action: PayloadAction<CreateCheckoutSessionResponse>) => {
        state.toppingUp = false;
        // Checkout is only created here. Balance changes after the hosted
        // Mercado Pago session is approved and the canonical result is read.
        void action.payload;
      })
      .addCase(topUp.rejected, (state, action) => {
        state.toppingUp = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearWalletError, setBalance } = walletSlice.actions;
export default walletSlice.reducer;
