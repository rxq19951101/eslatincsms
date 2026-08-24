/**
 * 钱包相关 API（简化版）
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';
import {
  createWalletTopUpCheckoutSession,
  formatWalletTopUpAmount,
  listPaymentMethods,
} from './payments';
import type {
  CanonicalPaymentMethodsResponse,
  CreateCheckoutSessionResponse,
  WalletBalance,
  WalletTransaction,
} from '../types';

export async function getWalletBalance(): Promise<WalletBalance> {
  const res = await apiClient.get<WalletBalance>(API_ENDPOINTS.WALLET.BALANCE);
  return res.data;
}

export async function getWalletTransactions(params?: { limit?: number; offset?: number }): Promise<WalletTransaction[]> {
  const res = await apiClient.get<WalletTransaction[]>(API_ENDPOINTS.WALLET.TRANSACTIONS, { params });
  return res.data;
}

export async function topUpWallet(amount: number): Promise<CreateCheckoutSessionResponse> {
  return createWalletTopUpCheckoutSession(formatWalletTopUpAmount(amount));
}

/** 云端已保存支付方式：统一读取 canonical payment-methods projection。 */
export async function getSavedPaymentMethods(): Promise<CanonicalPaymentMethodsResponse> {
  return { items: await listPaymentMethods() };
}
