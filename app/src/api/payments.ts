/**
 * 支付相关 API（支持 Wompi 和 Mercado Pago）
 */

import axios from 'axios';
import apiClient, { handleApiError } from './client';
import { API_ENDPOINTS, MERCADOPAGO_PUBLIC_KEY } from '../constants/config';
import type { 
  CreatePaymentRequest, 
  CreatePaymentResponse, 
  CreateMercadoPagoPaymentRequest,
  MercadoPagoPaymentResponse,
  PaymentProviderCode,
  PaymentProviderOption,
  PaymentStatusResponse, 
  UnpaidCharge,
  CardData,
  MercadoPagoCardTokenResult,
} from '../types';

/**
 * BIN 回退推断 MP payment_method_id（优先以 card_tokens 响应为准）
 */
function inferPaymentMethodIdFromPan(panDigits: string): string {
  const d = panDigits.replace(/\D/g, '');
  if (d.length < 4) return 'visa';

  const first = d[0];
  const firstTwo = parseInt(d.slice(0, 2), 10);
  const firstThree = parseInt(d.slice(0, 3), 10);
  const firstFour = parseInt(d.slice(0, 4), 10);
  const firstSix = parseInt(d.slice(0, 6), 10);

  if (first === '4') return 'visa';

  if ((firstTwo >= 51 && firstTwo <= 55) || (firstFour >= 2221 && firstFour <= 2720)) {
    return 'master';
  }

  if (firstTwo === 34 || firstTwo === 37) return 'amex';

  if (firstFour === 6011 || firstTwo === 65) return 'master';

  if (firstTwo === 36 || firstTwo === 38 || firstThree === 300 || firstThree === 305) {
    return 'diners_club_international';
  }

  if (firstSix >= 506776 && firstSix <= 506778) return 'master';

  return 'visa';
}

function extractPaymentMethodIdFromTokenPayload(
  data: Record<string, unknown>,
  panDigits: string
): string {
  const direct = data.payment_method_id;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();

  const pm = data.payment_method;
  if (pm && typeof pm === 'object') {
    const id = (pm as { id?: string }).id;
    if (typeof id === 'string' && id.trim()) return id.trim();
  }

  const bin = data.first_six_digits;
  if (typeof bin === 'string' && bin.replace(/\D/g, '').length >= 6) {
    return inferPaymentMethodIdFromPan(bin);
  }

  return inferPaymentMethodIdFromPan(panDigits);
}

// Wompi 支付（保留兼容）
export async function createWompiPayment(req: CreatePaymentRequest): Promise<CreatePaymentResponse> {
  const res = await apiClient.post<CreatePaymentResponse>(API_ENDPOINTS.PAYMENTS.CREATE, req);
  return res.data;
}

export const PAYMENT_PROVIDER_OPTIONS: PaymentProviderOption[] = [
  {
    code: 'mercadopago',
    name: '信用卡支付',
    description: '由安全支付服务处理',
    enabled: true,
    supportedTypes: ['top_up', 'charging'],
  },
  {
    code: 'wompi',
    name: 'Wompi',
    description: '网页收银台支付',
    enabled: true,
    supportedTypes: ['top_up', 'charging'],
  },
];

// Mercado Pago 支付
/**
 * 获取 Card Token（前端直接调用 Mercado Pago API）
 * 
 * 注意：不要直接使用 fetch，建议使用官方 SDK 或 WebView + Secure Fields
 * 这里提供一个基础实现示例，生产环境应使用更安全的方式
 */
export async function getCardToken(cardData: CardData): Promise<MercadoPagoCardTokenResult> {
  if (!MERCADOPAGO_PUBLIC_KEY?.trim()) {
    throw new Error(
      'Mercado Pago public_key 为空：请在 app/.env 设置 EXPO_PUBLIC_MERCADOPAGO_PUBLIC_KEY，或在 app.json 的 expo.extra.mercadopagoPublicKey 配置'
    );
  }
  const response = await fetch(
    `https://api.mercadopago.com/v1/card_tokens?public_key=${encodeURIComponent(MERCADOPAGO_PUBLIC_KEY.trim())}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        card_number: cardData.number.replace(/\s/g, ''),
        expiration_month: cardData.expMonth,
        expiration_year: cardData.expYear,
        security_code: cardData.cvc,
        cardholder: {
          name: cardData.holderName,
        },
      }),
    }
  );

  const panDigits = cardData.number.replace(/\s/g, '');
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.message === 'string' ? error.message : 'Token creation failed'
    );
  }
  
  const data = (await response.json()) as Record<string, unknown>;
  const tokenId = data.id;
  if (typeof tokenId !== 'string' || !tokenId) {
    throw new Error('Token creation failed: No token ID returned');
  }

  const payment_method_id = extractPaymentMethodIdFromTokenPayload(data, panDigits);

  return { tokenId, payment_method_id };
}

/**
 * 创建 Mercado Pago 支付
 * 
 * 流程：
 * 1. 前端收集卡信息
 * 2. 调用 getCardToken 获取 token
 * 3. 生成 idempotency_key (UUID v4)
 * 4. 调用后端创建支付
 */
export async function createMercadoPagoPayment(
  amount: number,
  cardData: CardData,
  email: string,
  type: 'top_up' | 'charging',
  metadata?: { session_id?: number; charge_point_id?: string; site_id?: string }
): Promise<MercadoPagoPaymentResponse> {
  try {
    // 1. 获取 Card Token（含 MP 返回的 payment_method_id，非 Visa/Master 时避免乱猜）
    const { tokenId: token, payment_method_id } = await getCardToken(cardData);
    
    // 2. 生成幂等性键（UUID v4）
    const generateUUID = (): string => {
      // 使用 crypto.randomUUID 如果可用，否则生成 UUID v4
      if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
      }
      // Fallback: 生成 UUID v4 格式
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    };
    const idempotency_key = generateUUID();

    // 3. payment_method_id 已由 getCardToken（MP 响应或 BIN 回退）给出

    // 4. 调用后端创建支付
    const req: CreateMercadoPagoPaymentRequest = {
      type,
      amount,
      currency: 'COP',
      token,
      email,
      payment_method_id,
      idempotency_key,
      metadata,
    };
    
    const res = await apiClient.post<MercadoPagoPaymentResponse>(
      API_ENDPOINTS.PAYMENTS.CREATE_MP,
      req
    );
    return res.data;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.data != null) {
      console.error(
        '[create-mp] 后端响应:',
        JSON.stringify(error.response.data, null, 2),
        'HTTP',
        error.response.status
      );
    }
    const { message } = handleApiError(error);
    console.error('Error creating MercadoPago payment:', message);
    throw new Error(message || '创建 Mercado Pago 支付失败');
  }
}

export async function createPaymentByProvider(
  provider: PaymentProviderCode = 'mercadopago',
  params: {
    amount: number;
    type: 'top_up' | 'charging';
    metadata?: { session_id?: number; charge_point_id?: string; site_id?: string };
    cardData?: CardData;
    email?: string;
  }
): Promise<CreatePaymentResponse | MercadoPagoPaymentResponse> {
  if (provider === 'mercadopago') {
    if (!params.cardData || !params.email) {
      throw new Error('Mercado Pago 需要卡信息和邮箱');
    }
    return createMercadoPagoPayment(
      params.amount,
      params.cardData,
      params.email,
      params.type,
      params.metadata
    );
  }
  return createWompiPayment({
    type: params.type,
    amount: params.amount,
    currency: 'COP',
    metadata: params.metadata,
  });
}

export async function getPaymentOrderStatus(orderId: string): Promise<PaymentStatusResponse> {
  const res = await apiClient.get<PaymentStatusResponse>(API_ENDPOINTS.PAYMENTS.STATUS(orderId));
  return res.data;
}

export async function getUnpaidCharges(): Promise<UnpaidCharge[]> {
  const res = await apiClient.get<UnpaidCharge[]>(API_ENDPOINTS.WALLET.UNPAID_CHARGES);
  return res.data;
}

export async function payUnpaidCharge(sessionId: number): Promise<void> {
  await apiClient.post(API_ENDPOINTS.WALLET.PAY_UNPAID_CHARGE, { session_id: sessionId });
}
