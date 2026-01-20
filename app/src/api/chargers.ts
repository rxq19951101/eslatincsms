/**
 * 充电站API服务
 */

import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';

export interface Charger {
  id: string;
  vendor?: string;
  model?: string;
  site_name?: string;
  site_address?: string;
  latitude?: number;
  longitude?: number;
  status: string;
  price_per_kwh?: number;
  is_configured: boolean;
  has_location: boolean;
  has_pricing: boolean;
  last_seen?: string;
  available_connectors?: number;
  total_connectors?: number;
}

export interface ChargerDetail extends Charger {
  serial_number?: string;
  firmware_version?: string;
  connector_type?: string;
  charging_rate?: number;
  rating?: number;
  description?: string;
  connectors?: Array<{
    id: number;
    connector_id: number;
    status: string;
    power_kw?: number | null;
    connector_type?: string | null;
  }>;
}

export interface ChargersListParams {
  filter_type?: 'configured' | 'unconfigured';
  latitude?: number;
  longitude?: number;
  radius?: number;
  limit?: number;
  offset?: number;
}

/**
 * 获取充电站列表
 */
export const getChargers = async (params?: ChargersListParams): Promise<Charger[]> => {
  try {
    const response = await apiClient.get<Charger[]>(API_ENDPOINTS.CHARGERS.LIST, {
      params,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to fetch chargers:', error);
    throw error;
  }
};

/**
 * 获取充电站详情
 */
export const getChargerById = async (id: string): Promise<ChargerDetail> => {
  try {
    const response = await apiClient.get<ChargerDetail>(
      API_ENDPOINTS.CHARGERS.DETAIL(id)
    );
    return response.data;
  } catch (error) {
    console.error(`Failed to fetch charger ${id}:`, error);
    throw error;
  }
};

/**
 * 获取附近的充电站
 */
export const getNearbyChargers = async (
  latitude: number,
  longitude: number,
  radius: number = 5000
): Promise<Charger[]> => {
  try {
    const response = await apiClient.get<Charger[]>(API_ENDPOINTS.CHARGERS.NEARBY, {
      params: {
        latitude,
        longitude,
        radius,
      },
    });
    return response.data;
  } catch (error) {
    console.error('Failed to fetch nearby chargers:', error);
    // 如果附近充电站接口不存在，回退到普通列表
    return getChargers({ latitude, longitude, radius });
  }
};

/**
 * 将充电站数据转换为GeoJSON格式（用于地图显示）
 */
export const chargersToGeoJSON = (chargers: Charger[]) => {
  return {
    type: 'FeatureCollection',
    features: chargers
      .filter((charger) => charger.latitude && charger.longitude)
      .map((charger) => ({
        type: 'Feature',
        id: charger.id,
        geometry: {
          type: 'Point',
          coordinates: [charger.longitude!, charger.latitude!],
        },
        properties: {
          id: charger.id,
          name: charger.site_name || `Charger ${charger.id}`,
          address: charger.site_address || '',
          status: charger.status,
          price: charger.price_per_kwh || 0,
          available: charger.available_connectors || 0,
          total: charger.total_connectors || 0,
          vendor: charger.vendor || '',
          model: charger.model || '',
        },
      })),
  };
};

/**
 * 计算两个坐标之间的距离（单位：千米）
 */
export const calculateDistance = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number => {
  const R = 6371; // 地球半径（千米）
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const distance = R * c;
  return Math.round(distance * 10) / 10; // 保留1位小数
};
