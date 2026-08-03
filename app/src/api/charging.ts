/**
 * 扫码充电相关 API
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

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
    price_per_kwh?: number;
  };
}

export async function startChargingByScan(params: {
  qrToken: string;
}): Promise<RemoteResponse> {
  const res = await apiClient.post<RemoteResponse>(API_ENDPOINTS.CHARGING.START, {
    qr_token: params.qrToken,
  });
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
  balance: number;
  currency: string;
  charged_amount: number;
  energy_kwh?: number;
  price_per_kwh?: number;
}

export async function settleCharging(sessionId: string): Promise<SettleResult> {
  const res = await apiClient.post<SettleResult>(API_ENDPOINTS.CHARGING.SETTLE, {
    session_id: sessionId,
  });
  return res.data;
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
