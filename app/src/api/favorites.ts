import apiClient from './client';
import { API_ENDPOINTS } from '../constants/config';
import type { SiteSummary } from './sites';

export const getFavoriteSites = async (): Promise<SiteSummary[]> => {
  const response = await apiClient.get<SiteSummary[]>(API_ENDPOINTS.FAVORITES.LIST);
  return response.data;
};

export const saveFavoriteSite = async (siteId: string): Promise<void> => {
  await apiClient.put(API_ENDPOINTS.FAVORITES.DETAIL(siteId));
};

export const removeFavoriteSite = async (siteId: string): Promise<void> => {
  await apiClient.delete(API_ENDPOINTS.FAVORITES.DETAIL(siteId));
};
