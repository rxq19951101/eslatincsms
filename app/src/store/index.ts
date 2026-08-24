/**
 * Redux Store配置
 */

import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import chargerReducer from './slices/chargerSlice';
import chargingReducer from './slices/chargingSlice';
import walletReducer from './slices/walletSlice';
import transactionsReducer from './slices/transactionsSlice';
import siteReducer from './slices/siteSlice';
import { invalidateLocalSession } from './slices/authSlice';
import { configureSessionInvalidationHandler } from '../api/client';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    charger: chargerReducer,
    charging: chargingReducer,
    wallet: walletReducer,
    transactions: transactionsReducer,
    site: siteReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // 忽略某些action的序列化检查（如导航相关）
        ignoredActions: ['navigation/NAVIGATE'],
      },
    }),
});

configureSessionInvalidationHandler(() => {
  store.dispatch(invalidateLocalSession());
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
