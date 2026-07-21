import { describe, it, expect, beforeEach } from 'vitest';
import { getDefaultTenant, getTenantId, setCurrentTenantId, clearCurrentTenantId, requiresTenantSelection } from '../tenant';
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
      tenant_list: [{ id: 'default-tenant-id', name: 'Default tenant', is_primary: true }],
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
      setCurrentTenantId('default-tenant-id', mockUser.id);
      const tenantId = getTenantId(mockUser);
      expect(tenantId).toBe('default-tenant-id');
    });

    it('拒绝不属于用户的 localStorage 租户并回退默认租户', () => {
      setCurrentTenantId('foreign-tenant-id', mockUser.id);
      const tenantId = getTenantId(mockUser);
      expect(tenantId).toBe('default-tenant-id');
    });

    it('同一租户也不能继承其他管理员的显式选择', () => {
      setCurrentTenantId('default-tenant-id', 'previous-admin-id');

      expect(getTenantId(mockUser)).toBe('default-tenant-id');
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBeNull();
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

    it('普通管理员没有 default_tenant_id 时仍选择有效 primary membership', () => {
      const userWithoutTenant: AdminUser = {
        ...mockUser,
        default_tenant_id: undefined,
      };
      const tenantId = getTenantId(userWithoutTenant);
      expect(tenantId).toBe('default-tenant-id');
    });
  });

  describe('setCurrentTenantId', () => {
    it('应该把当前租户 ID 与管理员 ID 一起写入 localStorage', () => {
      setCurrentTenantId('test-tenant-id', 'admin-id');
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBe('test-tenant-id');
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBe('admin-id');
    });
  });

  describe('clearCurrentTenantId', () => {
    it('应该清除当前租户 ID', () => {
      setCurrentTenantId('test-tenant-id', 'admin-id');
      clearCurrentTenantId();
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_ID)).toBeNull();
      expect(localStorage.getItem(STORAGE_KEYS.CURRENT_TENANT_USER_ID)).toBeNull();
    });
  });

  describe('getDefaultTenant', () => {
    it('只从普通管理员的有效成员关系中选择 default/primary 租户', () => {
      const user: AdminUser = {
        id: 'admin-id',
        username: 'admin',
        email: 'admin@example.com',
        is_super_admin: false,
        default_tenant_id: 'missing-tenant',
        tenant_list: [
          { id: 'primary-tenant', name: 'Primary', is_primary: true },
          { id: 'other-tenant', name: 'Other', is_primary: false },
        ],
      };

      expect(getDefaultTenant(user)?.id).toBe('primary-tenant');
      expect(getDefaultTenant({ ...user, is_super_admin: true })).toBeNull();
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
