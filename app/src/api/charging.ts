/**
 * 扫码充电相关 API
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';
import type { PricingInfo } from '../utils/pricing';
import type { CreateCheckoutSessionRequest } from '../types';

export type ChargingSettlementMethod = 'wallet' | 'direct_card';

export interface ChargingPreflightResult {
  resource: {
    charge_point_id: string;
    site_id: string;
    connector_id: number;
    pricing_mode: 'paid' | 'free' | 'unavailable';
  };
  financial_eligibility: {
    operation: string;
    status: 'eligible' | 'blocked' | 'recheck_required' | 'unknown';
    reason_codes: string[];
    blocking_resources: Array<Record<string, string>>;
    allowed_actions: string[];
    evaluated_at: string;
    version: number;
  };
  rail_eligibility: {
    axis: string;
    status: 'open' | 'closed' | 'not_applicable' | 'unknown';
    matched_scope_refs: string[];
    evaluated_at: string;
    version: number;
  };
  decision: 'allowed' | 'blocked';
  allowed_actions: string[];
}

export async function chargingPreflight(params: {
  qrToken: string;
  settlementMethod: ChargingSettlementMethod;
}): Promise<ChargingPreflightResult> {
  const res = await apiClient.post<ChargingPreflightResult>('/api/v1/app/charging/preflight', {
    qr_token: params.qrToken,
    settlement_method: params.settlementMethod,
  });
  return res.data;
}

export function buildChargingDirectCheckoutRequest(params: {
  chargePointId: string;
  connectorId: number;
  savedPaymentMethodId?: string | null;
}): Omit<CreateCheckoutSessionRequest, 'idempotency_key' | 'return_url'> {
  const hasSavedPaymentMethod = Boolean(params.savedPaymentMethodId);
  return {
    purpose: 'charging_direct',
    payment_method_mode: hasSavedPaymentMethod ? 'saved_card' : 'new_card',
    saved_payment_method_id: params.savedPaymentMethodId ?? null,
    save_card: false,
    charge_point_id: params.chargePointId,
    connector_id: params.connectorId,
  };
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

function isAllowedChargingActionUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' && [...MERCADO_PAGO_ACTION_HOSTS].some(
      (host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`),
    );
  } catch {
    return false;
  }
}

export interface RemoteResponse {
  success: boolean;
  result?: 'accepted' | 'already_active';
  status?: 'accepted' | 'already_active';
  message?: string;
  session?: ActiveChargingSession;
  details?: any;
}

export interface ActiveChargingSession {
  id: string;
  transaction_id: number;
  charge_point_id: string;
  ocpp_identity?: string | null;
  connector_id?: number | null;
  evse_id: string;
  id_tag: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  meter_start: number;
  meter_stop: number | null;
}

export interface ChargerStatusCheck {
  charger_id: string;
  ocpp_identity?: string | null;
  connector_id: number;
  status: 'offline' | 'charging' | 'available';
  is_online: boolean;
  last_seen?: string;
  connector_status: string;
  active_session?: {
    session_id: string;
    user_id: string;
    is_current_user: boolean;
    start_time: string;
  };
  charger_info?: {
    vendor?: string;
    model?: string;
    site_name?: string;
    site_address?: string;
    price_per_kwh?: number | null;
    pricing?: PricingInfo;
  };
}

export async function startChargingByScan(params: {
  qrToken: string;
  settlementMethod?: ChargingSettlementMethod;
  paymentIntentId?: string | null;
}): Promise<RemoteResponse> {
  const payload: {
    qr_token: string;
    settlement_method?: ChargingSettlementMethod;
    payment_intent_id?: string;
  } = {
    qr_token: params.qrToken,
  };
  if (params.settlementMethod) payload.settlement_method = params.settlementMethod;
  if (params.paymentIntentId) payload.payment_intent_id = params.paymentIntentId;

  const res = await apiClient.post<RemoteResponse>(API_ENDPOINTS.CHARGING.START, payload);
  return {
    ...res.data,
    session: normalizeActiveSession(res.data.session),
  };
}

type RawActiveSession = Partial<ActiveChargingSession> & { session_id?: string };

function normalizeActiveSession(
  value: RawActiveSession | null | undefined
): ActiveChargingSession | undefined {
  if (!value) return undefined;
  const id = value.id || value.session_id;
  if (!id) return undefined;
  return {
    id,
    transaction_id: value.transaction_id ?? 0,
    charge_point_id: value.charge_point_id || '',
    ocpp_identity: value.ocpp_identity,
    evse_id: value.evse_id || String(value.connector_id ?? ''),
    connector_id: value.connector_id,
    id_tag: value.id_tag || '',
    start_time: value.start_time ?? null,
    end_time: value.end_time ?? null,
    status: value.status || 'ongoing',
    meter_start: value.meter_start ?? 0,
    meter_stop: value.meter_stop ?? null,
  };
}

export async function checkChargerStatus(qrToken: string): Promise<ChargerStatusCheck> {
  const res = await apiClient.get<ChargerStatusCheck>(API_ENDPOINTS.CHARGING.CHECK, {
    params: { qr_token: qrToken },
  });
  return res.data;
}

export async function getActiveChargingSession(qrToken?: string): Promise<ActiveChargingSession | null> {
  try {
    const res = qrToken
      ? await apiClient.get<ActiveChargingSession>(API_ENDPOINTS.CHARGING.ACTIVE, {
          params: { qr_token: qrToken },
        })
      : await apiClient.get<ActiveChargingSession>(API_ENDPOINTS.CHARGING.ACTIVE);
    const data = res.data as RawActiveSession | {
      session?: RawActiveSession | null;
    };
    if (data && typeof data === 'object' && 'session' in data) {
      return normalizeActiveSession(data.session) ?? null;
    }
    return normalizeActiveSession(data as RawActiveSession) ?? null;
  } catch (e: any) {
    // 404 表示当前没有 active session
    const status = e?.response?.status;
    if (status === 404) return null;
    throw e;
  }
}

export async function stopCharging(sessionId: string): Promise<RemoteResponse> {
  const res = await apiClient.post<RemoteResponse>(API_ENDPOINTS.CHARGING.STOP, {
    session_id: sessionId,
  });
  return res.data;
}

export interface SettleResult {
  already_settled: boolean;
  balance: string | null;
  currency: string;
  charged_amount: string;
  energy_kwh: string;
  price_per_kwh: string;
  invoice_id?: string | null;
  settlement_method: 'wallet' | 'direct_card' | 'free';
  payment_status: 'processing' | 'action_required' | 'paid' | 'unpaid';
  payment_order_id?: string | null;
  next_action?: { type: 'open_url'; url: string } | null;
}

export async function settleCharging(sessionId: string): Promise<SettleResult> {
  const res = await apiClient.post<Partial<SettleResult> & {
    charged_amount?: string | number;
    balance?: string | number | null;
    energy_kwh?: string | number;
    price_per_kwh?: string | number;
    next_action?: { type?: string; url?: string } | null;
  }>(API_ENDPOINTS.CHARGING.SETTLE, {
    session_id: sessionId,
  });
  const data = res.data;
  const nextAction = data.next_action?.type === 'open_url' &&
    isAllowedChargingActionUrl(data.next_action.url)
    ? { type: 'open_url' as const, url: data.next_action.url }
    : null;

  return {
    already_settled: Boolean(data.already_settled),
    balance: data.balance === null || data.balance === undefined ? null : String(data.balance),
    currency: data.currency || 'COP',
    charged_amount: String(data.charged_amount ?? '0.00'),
    energy_kwh: String(data.energy_kwh ?? '0'),
    price_per_kwh: String(data.price_per_kwh ?? '0.00'),
    invoice_id: data.invoice_id ?? null,
    settlement_method: data.settlement_method === 'direct_card' || data.settlement_method === 'free'
      ? data.settlement_method
      : 'wallet',
    payment_status: data.payment_status === 'processing' ||
      data.payment_status === 'action_required' ||
      data.payment_status === 'unpaid'
      ? data.payment_status
      : 'paid',
    payment_order_id: data.payment_order_id ?? null,
    next_action: nextAction,
  };
}

export interface MeterValuePoint {
  id: string;
  source?: 'database' | 'realtime';
  timestamp: string | null;
  connector_id: number | null;
  value_wh: number;
  energy_kwh: number | null;
  power_kw: number | null;
  current_a: number | null;
  voltage_v: number | null;
  soc: number | null;
  sampled_value?: any;
}

export async function getMeterValues(params: {
  sessionId: string;
  sinceId?: string;
  limit?: number;
}): Promise<MeterValuePoint[]> {
  const res = await apiClient.get<MeterValuePoint[]>(API_ENDPOINTS.CHARGING.METER_VALUES, {
    params: {
      session_id: params.sessionId,
      since_id: params.sinceId,
      limit: params.limit ?? 50,
    },
  });
  return res.data;
}
