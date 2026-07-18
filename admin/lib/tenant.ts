import { STORAGE_KEYS } from './constants';
import { AdminUser } from '@/types';

/**
 * 获取当前租户 ID（按优先级）
 * 优先级：localStorage > default_tenant > super_admin (null)
 * 租户切换必须通过受控选择器完成，不接受 URL 直接覆盖工作上下文。
 */
export function getTenantId(userInfo: AdminUser | null | undefined): string | null {
  if (typeof window === 'undefined') return null;

  // 优先级 1: localStorage（用户通过租户选择器选择）
  const localStorageTenantId = localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID);
  if (localStorageTenantId && (
    userInfo?.is_super_admin || userInfo?.tenant_list?.some((t) => t.id === localStorageTenantId)
  )) {
    return localStorageTenantId;
  }

  // 优先级 2: 用户默认租户（从用户信息获取）
  if (userInfo?.default_tenant_id) {
    return userInfo.default_tenant_id;
  }

  // 优先级 3: super_admin 不传 tenant_id 表示全局作用域
  if (userInfo?.is_super_admin) {
    return null; // super_admin 可以不传 tenant_id
  }

  // 如果都没有且不是 super_admin，返回 null，触发跳转到租户选择页
  return null;
}

/**
 * 设置当前租户 ID 到 localStorage
 */
export function setCurrentTenantId(tenantId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEYS.CURRENT_TENANT_ID, tenantId);
}

/**
 * 清除当前租户 ID
 */
export function clearCurrentTenantId(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(STORAGE_KEYS.CURRENT_TENANT_ID);
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
