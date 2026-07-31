import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

export interface SiteSummary {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  status: string;
  charger_count: number;
  available_connectors: number;
  total_connectors: number;
  status_counts?: SiteStatusCounts;
  connector_types: string[];
  charging_options: SiteChargingOption[];
  max_power_kw?: number | null;
  price_per_kwh?: number | null;
  has_pricing: boolean;
  distance_km?: number;
  is_favorite: boolean;
}

export interface SiteChargingOption {
  standard: string;
  current_type?: 'AC' | 'DC' | null;
  max_power_kw?: number | null;
  available: number;
  total: number;
  status_counts?: SiteStatusCounts;
}

export interface SiteStatusCounts {
  available: number;
  charging: number;
  offline: number;
  faulted: number;
  occupied: number;
  unavailable: number;
  unknown: number;
}

export interface SiteConnector {
  id: string;
  connector_number: number;
  physical_reference?: string | null;
  status: string;
  connector_type?: string | null;
  power_kw?: number | null;
}

export interface SiteChargePoint {
  id: string;
  display_code: string;
  display_name?: string | null;
  location_hint?: string | null;
  status: string;
  vendor?: string | null;
  model?: string | null;
  connectors: SiteConnector[];
}

export interface SiteDetail extends SiteSummary {
  charge_points: SiteChargePoint[];
}

export interface SitesListParams {
  latitude?: number;
  longitude?: number;
  radius?: number;
  limit?: number;
}

export const getSites = async (params?: SitesListParams): Promise<SiteSummary[]> => {
  const response = await apiClient.get<SiteSummary[]>(API_ENDPOINTS.SITES.LIST, { params });
  return response.data;
};

export const getSiteById = async (id: string): Promise<SiteDetail> => {
  const response = await apiClient.get<SiteDetail>(API_ENDPOINTS.SITES.DETAIL(id));
  return response.data;
};
