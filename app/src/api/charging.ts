/**
 * 扫码充电相关 API
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

export interface RemoteResponse {
  success: boolean;
  message: string;
  details?: any;
}

export interface ActiveChargingSession {
  id: number;
  transaction_id: number;
  charge_point_id: string;
  evse_id: number;
  id_tag: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  meter_start: number;
  meter_stop: number | null;
}

export async function startChargingByScan(params: {
  chargePointId: string;
  connectorId: number;
}): Promise<RemoteResponse> {
  const res = await apiClient.post<RemoteResponse>(API_ENDPOINTS.CHARGING.START, {
    charge_point_id: params.chargePointId,
    connector_id: params.connectorId,
  });
  return res.data;
}

export async function getActiveChargingSession(chargePointId: string): Promise<ActiveChargingSession | null> {
  try {
    const res = await apiClient.get<ActiveChargingSession>(API_ENDPOINTS.CHARGING.ACTIVE, {
      params: { charge_point_id: chargePointId },
    });
    return res.data;
  } catch (e: any) {
    // 404 表示当前没有 active session
    const status = e?.response?.status;
    if (status === 404) return null;
    throw e;
  }
}

export async function stopCharging(chargePointId: string): Promise<RemoteResponse> {
  const res = await apiClient.post<RemoteResponse>(API_ENDPOINTS.CHARGING.STOP, {
    charge_point_id: chargePointId,
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

export async function settleCharging(sessionId: number): Promise<SettleResult> {
  const res = await apiClient.post<SettleResult>(API_ENDPOINTS.CHARGING.SETTLE, {
    session_id: sessionId,
  });
  return res.data;
}

export interface MeterValuePoint {
  id: number;
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
  sessionId: number;
  sinceId?: number;
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

