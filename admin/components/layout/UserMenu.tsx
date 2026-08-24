'use client';

import { useRouter } from 'next/navigation';
import useSWR, { mutate as mutateSWR } from 'swr';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { LogOut, User, Settings, Building2 } from 'lucide-react';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getRefreshToken, redirectToLogin } from '@/lib/auth';
import { Tenant, TenantRecord } from '@/types';
import { useI18n } from '@/lib/i18n';

export function UserMenu() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { currentTenant, setCurrentTenant } = useTenantStore();
  const { t } = useI18n();
  const { data: platformTenants } = useSWR<TenantRecord[]>(
    user?.is_super_admin ? API_ENDPOINTS.TENANTS : null,
    (url: string) => apiGet<TenantRecord[]>(url, { skipTenantId: true }),
  );

  const availableTenants: Tenant[] = user?.is_super_admin
    ? (platformTenants || []).map((tenant) => ({ id: tenant.id, name: tenant.name, is_primary: false }))
    : (user?.tenant_list || []);

  const handleLogout = async () => {
    try {
      const refreshToken = getRefreshToken();
      if (refreshToken) {
        // 调用后端撤销 token（可选）
        await apiPost(API_ENDPOINTS.AUTH_LOGOUT, { refresh_token: refreshToken }, {
          skipAuth: false,
          skipTenantId: true,
        });
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // authStore 统一清除 token、认证状态和租户内存/localStorage。
      logout();
      redirectToLogin();
    }
  };

  const handleSwitchTenant = async (tenant: Tenant | null) => {
    if (!user || tenant?.id === currentTenant?.id || (!tenant && !currentTenant)) return;
    setCurrentTenant(tenant, user.id);
    // 租户上下文变化后，重新验证所有页面数据，避免沿用旧租户缓存。
    await mutateSWR(() => true, undefined, { revalidate: true });
    router.refresh();
  };

  const getInitials = () => {
    if (user?.username) {
      return user.username.substring(0, 2).toUpperCase();
    }
    if (user?.full_name) {
      return user.full_name.substring(0, 2).toUpperCase();
    }
    return 'A';
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="flex items-center gap-3 h-auto p-2 hover:bg-slate-800"
        >
          <Avatar className="h-8 w-8">
            <AvatarFallback className="bg-gradient-to-br from-purple-600 to-blue-600 text-white text-sm">
              {getInitials()}
            </AvatarFallback>
          </Avatar>
          <div className="hidden md:block text-left">
            <p className="text-sm font-medium text-slate-200">{user?.username || t('administrator')}</p>
            <p className="text-xs text-slate-400">
              {currentTenant?.name || (user?.is_super_admin ? t('allPlatform') : t('未选择租户'))}
            </p>
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56 bg-slate-800 border-slate-700">
        <DropdownMenuLabel className="text-slate-200">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium">{user?.username || t('administrator')}</p>
            <p className="text-xs text-slate-400">{user?.email || ''}</p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-slate-700" />
        
        {(user?.is_super_admin || availableTenants.length > 1) && (
          <>
            <DropdownMenuLabel className="text-xs text-slate-400">{t('切换租户')}</DropdownMenuLabel>
            {user?.is_super_admin && (
              <DropdownMenuItem
                onClick={() => handleSwitchTenant(null)}
                className="text-slate-300 hover:bg-slate-700 hover:text-slate-100 cursor-pointer"
              >
                <Building2 className="mr-2 h-4 w-4" />
                {t('allPlatform')}{!currentTenant ? `（${t('当前')}）` : ''}
              </DropdownMenuItem>
            )}
            {availableTenants.map((tenant) => (
              <DropdownMenuItem
                key={tenant.id}
                onClick={() => handleSwitchTenant(tenant)}
                className="text-slate-300 hover:bg-slate-700 hover:text-slate-100 cursor-pointer"
              >
                <Building2 className="mr-2 h-4 w-4" />
                {tenant.name}{tenant.id === currentTenant?.id ? `（${t('当前')}）` : ''}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator className="bg-slate-700" />
          </>
        )}
        
        <DropdownMenuItem
          onClick={() => router.push('/settings')}
          className="text-slate-300 hover:bg-slate-700 hover:text-slate-100 cursor-pointer"
        >
          <Settings className="mr-2 h-4 w-4" />
          {t('个人设置')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => router.push('/settings')}
          className="text-slate-300 hover:bg-slate-700 hover:text-slate-100 cursor-pointer"
        >
          <User className="mr-2 h-4 w-4" />
          {t('个人信息')}
        </DropdownMenuItem>
        <DropdownMenuSeparator className="bg-slate-700" />
        <DropdownMenuItem
          onClick={handleLogout}
          className="text-red-400 hover:bg-slate-700 hover:text-red-300 cursor-pointer"
        >
          <LogOut className="mr-2 h-4 w-4" />
          {t('logout')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
