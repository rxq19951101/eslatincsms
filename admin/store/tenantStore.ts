import { create } from 'zustand';
import { Tenant } from '@/types';
import { setCurrentTenantId, clearCurrentTenantId } from '@/lib/tenant';

interface TenantState {
  currentTenant: Tenant | null;
  setCurrentTenant: (tenant: Tenant | null, userId: string | null) => void;
  getCurrentTenantId: () => string | null;
  clearTenant: () => void;
}

export const useTenantStore = create<TenantState>((set, get) => ({
  currentTenant: null,
  setCurrentTenant: (tenant, userId) => {
    if (tenant && userId) {
      setCurrentTenantId(tenant.id, userId);
      set({ currentTenant: tenant });
    } else {
      clearCurrentTenantId();
      set({ currentTenant: null });
    }
  },
  getCurrentTenantId: () => get().currentTenant?.id || null,
  clearTenant: () => {
    clearCurrentTenantId();
    set({ currentTenant: null });
  },
}));
