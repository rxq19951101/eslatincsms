import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AdminUser } from '@/types';
import { clearTokens } from '@/lib/auth';
import { useTenantStore } from './tenantStore';

interface AuthState {
  user: AdminUser | null;
  hasHydrated: boolean;
  setUser: (user: AdminUser | null) => void;
  setHasHydrated: (hasHydrated: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      hasHydrated: false,
      setUser: (user) => {
        if (get().user?.id !== user?.id) {
          useTenantStore.getState().clearTenant();
        }
        set({ user });
      },
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
      logout: () => {
        clearTokens();
        useTenantStore.getState().clearTenant();
        set({ user: null });
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      // 只持久化 user，token 单独存储在 localStorage
      partialize: (state) => ({ user: state.user }),
      onRehydrateStorage: (state) => () => {
        // 即使持久化数据损坏，也必须结束 hydration，后续按 token 走 /me 恢复。
        state.setHasHydrated(true);
      },
    }
  )
);
