import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AdminUser } from '@/types';
import { getAccessToken, clearTokens } from '@/lib/auth';

interface AuthState {
  user: AdminUser | null;
  setUser: (user: AdminUser | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      setUser: (user) => {
        set({
          user,
        });
      },
      logout: () => {
        clearTokens();
        set({
          user: null,
        });
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      // 只持久化 user，token 单独存储在 localStorage
      partialize: (state) => ({ user: state.user }),
    }
  )
);