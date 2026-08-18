import { describe, it, expect, beforeEach, vi, afterEach, beforeAll, afterAll } from 'vitest';
import { apiDelete, apiGet, apiPost } from '../api';
import { setTokens, clearTokens } from '../auth';
import { setCurrentTenantId } from '../tenant';
import { server } from '@/__mocks__/server';

// Mock fetch（直接 mock，不依赖 MSW）
const mockFetch = vi.fn();

// Mock useAuthStore
vi.mock('@/store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      user: {
        id: '1',
        username: 'admin',
        email: 'admin@example.com',
        is_super_admin: false,
        default_tenant_id: 'tenant-1',
        tenant_list: [{ id: 'tenant-1', name: 'Tenant 1', is_primary: true }],
      },
      logout: vi.fn(),
    })),
  },
}));

// 在 API 测试中，暂时禁用 MSW，使用直接的 fetch mock
beforeAll(() => {
  server.close(); // 关闭 MSW server，使用直接的 fetch mock
  global.fetch = mockFetch as unknown as typeof fetch;
});

afterAll(() => {
  // 测试结束后，恢复 MSW（为其他测试）
  server.listen({ onUnhandledRequest: 'bypass' });
});

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTokens();
    setCurrentTenantId('tenant-1', '1');
    // 确保使用 mock fetch
    global.fetch = mockFetch as unknown as typeof fetch;
  });

  afterEach(() => {
    mockFetch.mockClear();
  });

  describe('apiGet', () => {
    it('应该发送 GET 请求并注入 token', async () => {
      setTokens('test-access-token', 'test-refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ data: 'test' }),
      });

      await apiGet('/test');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-access-token',
            'X-Tenant-Id': 'tenant-1',
          }),
        })
      );
    });

    it('parses the frozen PAY-MP-002 vendor +json Audit projection as JSON', async () => {
      setTokens('test-access-token', 'test-refresh-token');
      const auditPage = {
        items: [{
          event_id: 'audit-1',
          actor: null,
          resource: { type: 'chargeback_case', id: 'case-1' },
          action: 'view',
          result: 'success',
          scope: { type: 'platform', ref: 'platform:eslatin' },
          reason_code: null,
          safe_metadata: { source: 'admin' },
          occurred_at: '2026-08-16T12:00:00Z',
        }],
        page: { next_cursor: null, has_more: false },
      };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'Application/Vnd.Eslatin.Pay-Mp-002.V1+Json; charset=utf-8' }),
        json: async () => auditPage,
        text: async () => JSON.stringify(auditPage),
      });

      await expect(apiGet('/api/v1/admin/audit-events')).resolves.toEqual(auditPage);
    });
  });

  describe('apiPost', () => {
    it('应该发送 POST 请求并包含 body', async () => {
      setTokens('test-access-token', 'test-refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ data: 'success' }),
      });

      await apiPost('/test', { key: 'value' }, { skipAuth: true });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ key: 'value' }),
          headers: expect.objectContaining({
            'X-Tenant-Id': 'tenant-1',
          }),
        })
      );
    });
  });

  describe('apiDelete', () => {
    it('应该发送 DELETE 请求并包含确认 body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
      });

      await apiDelete('/test', { confirmation: 'CP-01', reason: 'Created by mistake' });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'DELETE',
          body: JSON.stringify({ confirmation: 'CP-01', reason: 'Created by mistake' }),
        })
      );
    });
  });

  describe('401 自动刷新', () => {
    it('应该在 401 时自动刷新 token 并重试', async () => {
      setTokens('expired-token', 'refresh-token');

      // 第一次请求返回 401
      mockFetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ detail: 'Unauthorized' }),
        })
        // 刷新 token 请求
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            access_token: 'new-access-token',
            refresh_token: 'new-refresh-token',
          }),
        })
        // 重试的原始请求
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ data: 'success' }),
        });

      const result = await apiGet('/test', { skipTenantId: true });

      // 应该调用 3 次：原始请求、刷新 token、重试请求
      expect(mockFetch).toHaveBeenCalledTimes(3);
      expect(result).toEqual({ data: 'success' });
    });
  });
});
