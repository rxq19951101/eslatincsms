import { STORAGE_KEYS } from './constants';
import { AdminUser, Tenant } from '@/types';

/**
 * 普通租户管理员的初始租户只能来自当前账号的有效成员关系。
 */
export function getDefaultTenant(userInfo: AdminUser | null | undefined): Tenant | null {
  if (!userInfo || userInfo.is_super_admin) return null;

  return (
    (userInfo.default_tenant_id
      ? userInfo.tenant_list?.find((tenant) => tenant.id === userInfo.default_tenant_id)
      : undefined) ||
    userInfo.tenant_list?.find((tenant) => tenant.is_primary) ||
    userInfo.tenant_list?.[0] ||
    null
  );
}

/**
 * 获取当前租户 ID（按优先级）
 * 优先级：当前账号显式选择的 localStorage > 当前账号有效的 default/primary tenant
 * 租户切换必须通过受控选择器完成，不接受 URL 直接覆盖工作上下文。
 */
export function getTenantId(userInfo: AdminUser | null | undefined): string | null {
  if (typeof window === 'undefined') return null;

  // localStorage 中的选择必须同时属于当前管理员，避免账号切换后继承前一账号上下文。
  const localStorageTenantId = localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID);
  const localStorageUserId = localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID);
  if (localStorageTenantId && (
    localStorageUserId === userInfo?.id &&
    (userInfo?.is_super_admin || userInfo?.tenant_list?.some((t) => t.id === localStorageTenantId))
  )) {
    return localStorageTenantId;
  }

  if (localStorageTenantId || localStorageUserId) {
    clearCurrentTenantId();
  }

  // super_admin 未通过选择器显式选择时始终保持全平台视角。
  if (userInfo?.is_super_admin) {
    return null;
  }

  return getDefaultTenant(userInfo)?.id || null;
}

/**
 * 设置当前租户 ID 到 localStorage
 */
export function setCurrentTenantId(tenantId: string, userId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEYS.CURRENT_TENANT_ID, tenantId);
  localStorage.setItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID, userId);
}

/**
 * 清除当前租户 ID
 */
export function clearCurrentTenantId(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(STORAGE_KEYS.CURRENT_TENANT_ID);
  localStorage.removeItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID);
}

/**
 * 检查是否需要选择租户
 */
export function requiresTenantSelection(userInfo?: AdminUser | null): boolean {
  if (!userInfo) return true;
  if (userInfo.is_super_admin) return false;
  
  const tenantId = getTenantId(userInfo);
  return !tenantId;
}
