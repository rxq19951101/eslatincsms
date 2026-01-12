/**
 * 支付方式本地存储（简化版）
 * - 先不接真实支付网关，方便前端页面先跑通
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../constants/config';
import type { PaymentMethod } from '../types';

const STORAGE_KEY = STORAGE_KEYS.PAYMENT_METHODS;

export async function getPaymentMethods(): Promise<PaymentMethod[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as PaymentMethod[];
  } catch {
    return [];
  }
}

export async function savePaymentMethods(methods: PaymentMethod[]): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(methods));
}

export async function addPaymentMethod(method: PaymentMethod): Promise<PaymentMethod[]> {
  const methods = await getPaymentMethods();
  const next = [method, ...methods];
  await savePaymentMethods(next);
  return next;
}

export async function deletePaymentMethod(id: string): Promise<PaymentMethod[]> {
  const methods = await getPaymentMethods();
  const next = methods.filter((m) => m.id !== id);
  // 如果删除了默认卡，自动把第一张设为默认
  if (next.length > 0 && !next.some((m) => m.is_default)) {
    next[0] = { ...next[0], is_default: true };
  }
  await savePaymentMethods(next);
  return next;
}

export async function setDefaultPaymentMethod(id: string): Promise<PaymentMethod[]> {
  const methods = await getPaymentMethods();
  const next = methods.map((m) => ({ ...m, is_default: m.id === id }));
  await savePaymentMethods(next);
  return next;
}

