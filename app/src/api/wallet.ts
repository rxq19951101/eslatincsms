/**
 * 钱包相关 API（简化版）
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';
import type { SavedPaymentMethodsResponse, WalletBalance, WalletTransaction } from '../types';

export async function getWalletBalance(): Promise<WalletBalance> {
  const res = await apiClient.get<WalletBalance>(API_ENDPOINTS.WALLET.BALANCE);
  return res.data;
}

export async function getWalletTransactions(params?: { limit?: number; offset?: number }): Promise<WalletTransaction[]> {
  const res = await apiClient.get<WalletTransaction[]>(API_ENDPOINTS.WALLET.TRANSACTIONS, { params });
  return res.data;
}

export async function topUpWallet(amount: number): Promise<WalletBalance> {
  const idempotency_key =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `topup-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const res = await apiClient.post<WalletBalance>(API_ENDPOINTS.WALLET.TOP_UP, {
    amount,
    idempotency_key,
  });
  return res.data;
}

/** 云端已保存支付方式（当前多为空列表；绑卡接入后回填） */
export async function getSavedPaymentMethods(): Promise<SavedPaymentMethodsResponse> {
  const res = await apiClient.get<SavedPaymentMethodsResponse>(
    API_ENDPOINTS.WALLET.SAVED_PAYMENT_METHODS
  );
  return res.data;
}
