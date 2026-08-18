/**
 * 支付相关 API。
 *
 * App 只使用 Checkout Session；Provider 选择和凭证解析留在服务端。
 */

import axios from 'axios';
import apiClient from './client';
import { API_ENDPOINTS, API_BASE_URL } from '../constants/config';
import type { 
  CreatePaymentRequest,
  CreatePaymentResponse,
  PaymentStatusResponse, 
  UnpaidCharge,
  CanonicalPaymentMethod,
  CanonicalPaymentMethodsResponse,
  SaveCardCheckoutSessionRequest,
  SaveCardCheckoutSessionResponse,
  CreateCheckoutSessionRequest,
  CreateCheckoutSessionResponse,
  CheckoutSessionResponse,
  PaymentCheckoutStatus,
} from '../types';

export type { UnpaidCharge } from '../types';

const PAYMENT_METHODS_ENDPOINT = '/api/v1/app/payment-methods';
const CHECKOUT_SESSIONS_ENDPOINT = '/api/v1/app/payments/checkout-sessions';
const NATIVE_PAYMENT_RETURN_URL = 'eslatin://payment-return';
const CONFIGURED_WEB_PAYMENT_RETURN_URL = process.env.EXPO_PUBLIC_WEB_PAYMENT_RETURN_URL?.trim();
const WEB_PAYMENT_RETURN_URL =
  CONFIGURED_WEB_PAYMENT_RETURN_URL ||
  (process.env.NODE_ENV === 'production' ? undefined : 'http://localhost:8081/payment-return');
export const PAYMENT_RETURN_URL =
  typeof window !== 'undefined' && window.location?.protocol.startsWith('http')
    ? WEB_PAYMENT_RETURN_URL || NATIVE_PAYMENT_RETURN_URL
    : NATIVE_PAYMENT_RETURN_URL;

export type PaymentMethodTypeLabelKey =
  | 'creditCard'
  | 'debitCard'
  | 'prepaidCard'
  | 'bankCard';

export type CheckoutQueryErrorKind =
  | 'expired_or_missing'
  | 'already_submitted'
  | 'temporarily_unavailable'
  | 'network_unknown';

/** Keep credit/debit/prepaid/null and unexpected runtime values consistent across screens. */
export function getPaymentMethodTypeLabelKey(value: unknown): PaymentMethodTypeLabelKey {
  if (value === 'credit_card') return 'creditCard';
  if (value === 'debit_card') return 'debitCard';
  if (value === 'prepaid_card') return 'prepaidCard';
  return 'bankCard';
}

/** Map transport failures to safe recovery decisions without exposing provider messages. */
export function classifyCheckoutQueryError(error: unknown): CheckoutQueryErrorKind {
  if (!axios.isAxiosError(error)) return 'network_unknown';

  const status = error.response?.status;
  const data = error.response?.data as { detail?: { code?: unknown } } | undefined;
  const code = typeof data?.detail?.code === 'string' ? data.detail.code : '';

  if (status === 404 || code === 'CHECKOUT_SESSION_NOT_FOUND') return 'expired_or_missing';
  if (status === 409 || code === 'CHECKOUT_ALREADY_CONFIRMED') return 'already_submitted';
  if (status === 503 || code === 'CHECKOUT_UNAVAILABLE') return 'temporarily_unavailable';
  return 'network_unknown';
}

export function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.random() * 16 | 0;
    const value = character === 'x' ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

function isNotFoundError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}

/** Read the server-owned payment-method projection. No local demo storage is consulted. */
export async function listPaymentMethods(): Promise<CanonicalPaymentMethod[]> {
  const res = await apiClient.get<CanonicalPaymentMethodsResponse>(PAYMENT_METHODS_ENDPOINT);
  return res.data.items;
}

/** Set a payment method as default using the contract's idempotency header. */
export async function setPaymentMethodDefault(paymentMethodId: string): Promise<CanonicalPaymentMethod> {
  const res = await apiClient.patch<CanonicalPaymentMethod>(
    `${PAYMENT_METHODS_ENDPOINT}/${encodeURIComponent(paymentMethodId)}`,
    { is_default: true },
    { headers: { 'Idempotency-Key': createIdempotencyKey() } },
  );
  return res.data;
}

/**
 * Delete a payment method. A server/provider 404 is intentionally idempotent:
 * the card is already absent from the user's canonical projection.
 */
export async function deletePaymentMethodRemote(paymentMethodId: string): Promise<void> {
  try {
    await apiClient.delete(`${PAYMENT_METHODS_ENDPOINT}/${encodeURIComponent(paymentMethodId)}`, {
      headers: { 'Idempotency-Key': createIdempotencyKey() },
    });
  } catch (error) {
    if (isNotFoundError(error)) return;
    throw error;
  }
}

/** Create the hosted save-card session. Card fields never cross the App API boundary. */
export async function createSaveCardCheckoutSession(): Promise<SaveCardCheckoutSessionResponse> {
  const payload: SaveCardCheckoutSessionRequest = {
    purpose: 'save_card',
    payment_method_mode: 'new_card',
    save_card: true,
    currency: 'COP',
    return_url: PAYMENT_RETURN_URL,
    idempotency_key: createIdempotencyKey(),
  };
  const res = await apiClient.post<SaveCardCheckoutSessionResponse>(
    CHECKOUT_SESSIONS_ENDPOINT,
    payload,
  );
  return res.data;
}

/** Create any contract-defined hosted checkout session without card data. */
export async function createCheckoutSession(
  request: Omit<CreateCheckoutSessionRequest, 'idempotency_key' | 'return_url'> & {
    idempotency_key?: string;
    return_url?: string;
  },
): Promise<CreateCheckoutSessionResponse> {
  const payload: CreateCheckoutSessionRequest = {
    ...request,
    return_url: request.return_url ?? PAYMENT_RETURN_URL,
    idempotency_key: request.idempotency_key ?? createIdempotencyKey(),
  };
  const res = await apiClient.post<CreateCheckoutSessionResponse>(
    CHECKOUT_SESSIONS_ENDPOINT,
    payload,
  );
  return res.data;
}

export async function createWalletTopUpCheckoutSession(
  amount: string,
): Promise<CreateCheckoutSessionResponse> {
  if (!/^\d+(?:\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) {
    throw new Error('invalid_top_up_amount');
  }
  return createCheckoutSession({
    purpose: 'wallet_top_up',
    payment_method_mode: 'new_card',
    save_card: false,
    amount,
    currency: 'COP',
  });
}

/** Convert the numeric amount used by the existing App navigation into a COP decimal string. */
export function formatWalletTopUpAmount(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) {
    throw new Error('invalid_top_up_amount');
  }
  return amount.toFixed(2);
}

export async function getCheckoutSession(
  checkoutSessionId: string,
): Promise<CheckoutSessionResponse> {
  const res = await apiClient.get<CheckoutSessionResponse>(
    `${CHECKOUT_SESSIONS_ENDPOINT}/${encodeURIComponent(checkoutSessionId)}`,
  );
  const session = res.data;
  const status = isPaymentCheckoutStatus(session.status) ? session.status : 'error';

  // Never expose an untrusted 3DS URL to navigation or a WebView.
  if (session.next_action && !isAllowedMercadoPagoActionUrl(session.next_action.url)) {
    return { ...session, status, next_action: null };
  }
  return { ...session, status };
}

export function isPaymentCheckoutStatus(value: unknown): value is PaymentCheckoutStatus {
  return [
    'created',
    'ready',
    'processing',
    'action_required',
    'approved',
    'declined',
    'expired',
    'error',
  ].includes(value as PaymentCheckoutStatus);
}

export function normalizePaymentReturnStatus(value: unknown): PaymentCheckoutStatus | undefined {
  return isPaymentCheckoutStatus(value) ? value : undefined;
}

const MERCADO_PAGO_ACTION_HOSTS = new Set([
  'mercadopago.com',
  'mercadopago.com.co',
  'mercadopago.com.ar',
  'mercadopago.com.br',
  'mercadopago.com.mx',
  'mercadopago.com.pe',
  'mercadopago.com.uy',
  'mercadopago.cl',
  'mercadopago.com.ec',
  'mercadopago.com.ve',
]);

export function isAllowedMercadoPagoActionUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'https:') return false;
    return [...MERCADO_PAGO_ACTION_HOSTS].some(
      (host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`),
    );
  } catch {
    return false;
  }
}

export function isSecureCheckoutUrl(value: string): boolean {
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}

/** Hosted checkout must remain on the configured EsLatin API origin. */
export function isServerCheckoutUrl(value: string): boolean {
  try {
    const checkoutUrl = new URL(value);
    const apiUrl = new URL(API_BASE_URL);

    if (checkoutUrl.origin !== apiUrl.origin) return false;
    if (checkoutUrl.protocol === 'https:') return true;

    // Local sandbox testing is intentionally limited to loopback HTTP. Production
    // builds still require HTTPS because a non-loopback HTTP checkout is never
    // accepted here.
    const loopbackHosts = new Set(['localhost', '127.0.0.1']);
    return (
      checkoutUrl.protocol === 'http:' &&
      loopbackHosts.has(checkoutUrl.hostname) &&
      loopbackHosts.has(apiUrl.hostname)
    );
  } catch {
    return false;
  }
}

// Legacy implementation retained only for the unregistered Wompi screen.
// No current App flow calls this function; new payment work must use
// createCheckoutSession/createWalletTopUpCheckoutSession.
export async function createWompiPayment(req: CreatePaymentRequest): Promise<CreatePaymentResponse> {
  const res = await apiClient.post<CreatePaymentResponse>(API_ENDPOINTS.PAYMENTS.CREATE, req);
  return res.data;
}

export async function getPaymentOrderStatus(orderId: string): Promise<PaymentStatusResponse> {
  const res = await apiClient.get<PaymentStatusResponse>(API_ENDPOINTS.PAYMENTS.STATUS(orderId));
  return res.data;
}

export async function getUnpaidCharges(): Promise<UnpaidCharge[]> {
  const res = await apiClient.get<UnpaidCharge[]>(API_ENDPOINTS.WALLET.UNPAID_CHARGES);
  return res.data;
}

export async function payUnpaidCharge(sessionId: string): Promise<void> {
  await apiClient.post(API_ENDPOINTS.WALLET.PAY_UNPAID_CHARGE, { session_id: sessionId });
}
