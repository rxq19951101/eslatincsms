/**
 * 充电记录（会话历史）API
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

export interface ChargingRecord {
  id: number;
  transaction_id: number;
  charge_point_id: string;
  evse_id: number;
  start_time: string | null;
  end_time: string | null;
  status: string;
  energy_kwh: number | null;
  duration_minutes: number | null;
  site_name?: string | null;
  site_address?: string | null;
}

export type ChargingRecordDetail = ChargingRecord & {
  meter_start?: number;
  meter_stop?: number | null;
};

export async function getChargingRecords(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ChargingRecord[]> {
  const res = await apiClient.get<ChargingRecord[]>(API_ENDPOINTS.TRANSACTIONS.LIST, { params });
  return res.data;
}

export async function getChargingRecordDetail(id: number): Promise<ChargingRecordDetail> {
  const res = await apiClient.get<ChargingRecordDetail>(API_ENDPOINTS.TRANSACTIONS.DETAIL(id));
  return res.data;
}

