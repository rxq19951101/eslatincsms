/**
 * 钱包相关 API（简化版）
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';
import type { WalletBalance, WalletTransaction } from '../types';

export async function getWalletBalance(): Promise<WalletBalance> {
  const res = await apiClient.get<WalletBalance>(API_ENDPOINTS.WALLET.BALANCE);
  return res.data;
}

export async function getWalletTransactions(params?: { limit?: number; offset?: number }): Promise<WalletTransaction[]> {
  const res = await apiClient.get<WalletTransaction[]>(API_ENDPOINTS.WALLET.TRANSACTIONS, { params });
  return res.data;
}

export async function topUpWallet(amount: number): Promise<WalletBalance> {
  const res = await apiClient.post<WalletBalance>(API_ENDPOINTS.WALLET.TOP_UP, { amount });
  return res.data;
}

