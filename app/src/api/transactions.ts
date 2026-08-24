/**
 * 充电记录（会话历史）API
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

export interface ChargingRecord {
  id: string;
  transaction_id: number;
  charge_point_id: string;
  ocpp_identity?: string | null;
  evse_id: string;
  connector_id?: number | null;
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
  invoice_number?: string | null;
  total_amount?: string | null;
  currency: string;
  billing_status?: string | null;
  connector_number?: number | null;
  connector_label?: string | null;
  charge_point_label?: string | null;
};

export async function getChargingRecords(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ChargingRecord[]> {
  const res = await apiClient.get<ChargingRecord[]>(API_ENDPOINTS.TRANSACTIONS.LIST, { params });
  return res.data;
}

export async function getChargingRecordDetail(id: string): Promise<ChargingRecordDetail> {
  const res = await apiClient.get<ChargingRecordDetail>(API_ENDPOINTS.TRANSACTIONS.DETAIL(id));
  return res.data;
}
