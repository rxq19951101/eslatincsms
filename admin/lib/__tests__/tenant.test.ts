import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getTenantId, setCurrentTenantId, clearCurrentTenantId, requiresTenantSelection } from '../tenant';
import { AdminUser } from '@/types';
import { STORAGE_KEYS } from '../constants';

describe('tenant utilities', () => {
  beforeEach(() => {
    // 清理 localStorage
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
    // 清理 URL 参数
    Object.defineProperty(window, 'location', {
      value: { search: '' },
      writable: true,
      configurable: true,
    });
  });

  describe('getTenantId - 受控上下文测试', () => {
    const mockUser: AdminUser = {
      id: '1',
      username: 'admin',
      email: 'admin@example.com',
      is_super_admin: false,
      default_tenant_id: 'default-tenant-id',
      tenant_list: [],
    };

    it('忽略 URL Query 参数，避免外部链接覆盖工作租户', () => {
      // 模拟 URL 参数
      Object.defineProperty(window, 'location', {
        value: { search: '?tenant=query-tenant-id' },
        writable: true,
        configurable: true,
      });
      
      const tenantId = getTenantId(mockUser);
      expect(tenantId).toBe('default-tenant-id');
    });

    it('只接受用户所属租户的 localStorage tenant_id', () => {
      localStorage.setItem(STORAGE_KEYS.CURRENT_TENANT_ID, 'default-tenant-id');
      const tenantId = getTenantId(mockUser);
      expect(tenantId).toBe('default-tenant-id');
    });

    it('拒绝不属于用户的 localStorage 租户并回退默认租户', () => {
      localStorage.setItem(STORAGE_KEYS.CURRENT_TENANT_ID, 'foreign-tenant-id');
      const tenantId = getTenantId(mockUser);
      expect(tenantId).toBe('default-tenant-id');
    });

    it('优先级4: super_admin 可以不传 tenant_id', () => {
      const superAdmin: AdminUser = {
        ...mockUser,
        is_super_admin: true,
        default_tenant_id: undefined,
      };
      const tenantId = getTenantId(superAdmin);
      expect(tenantId).toBeNull();
    });

    it('应该返回 null 如果不是 super_admin 且没有 tenant_id', () => {
      const userWithoutTenant: AdminUser = {
        ...mockUser,
        default_tenant_id: undefined,
      };
      const tenantId = getTenantId(userWithoutTenant);
      expect(tenantId).toBeNull();
    });
  });

  describe('setCurrentTenantId', () => {
    it('应该设置当前租户 ID 到 localStorage', () => {
      setCurrentTenantId('test-tenant-id');
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBe('test-tenant-id');
    });
  });

  describe('clearCurrentTenantId', () => {
    it('应该清除当前租户 ID', () => {
      setCurrentTenantId('test-tenant-id');
      clearCurrentTenantId();
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
    });
  });

  describe('requiresTenantSelection', () => {
    it('应该在用户没有 tenant 时返回 true', () => {
      expect(requiresTenantSelection(null)).toBe(true);
      expect(requiresTenantSelection(undefined)).toBe(true);
    });

    it('super_admin 不需要选择租户', () => {
      const superAdmin: AdminUser = {
        id: '1',
        username: 'admin',
        email: 'admin@example.com',
        is_super_admin: true,
        tenant_list: [],
      };
      expect(requiresTenantSelection(superAdmin)).toBe(false);
    });
  });
});
