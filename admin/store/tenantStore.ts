import { create } from 'zustand';
import { Tenant } from '@/types';
import { setCurrentTenantId, getTenantId, clearCurrentTenantId } from '@/lib/tenant';
import { useAuthStore } from './authStore';

interface TenantState {
  currentTenant: Tenant | null;
  setCurrentTenant: (tenant: Tenant | null) => void;
  getCurrentTenantId: () => string | null;
  clearTenant: () => void;
}

export const useTenantStore = create<TenantState>((set, get) => ({
  currentTenant: null,
  setCurrentTenant: (tenant) => {
    if (tenant) {
      setCurrentTenantId(tenant.id);
    } else {
      clearCurrentTenantId();
    }
    set({ currentTenant: tenant });
  },
  getCurrentTenantId: () => {
    const userInfo = useAuthStore.getState().user;
    return getTenantId(userInfo);
  },
  clearTenant: () => {
    clearCurrentTenantId();
    set({ currentTenant: null });
  },
}));