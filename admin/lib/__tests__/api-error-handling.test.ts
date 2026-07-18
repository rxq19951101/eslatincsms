import { describe, it, expect, vi, beforeEach, beforeAll, afterAll } from 'vitest';
import { ApiRequestError, apiGet } from '../api';
import { setTokens, clearTokens } from '../auth';
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
        tenant_list: [],
      },
      logout: vi.fn(),
    })),
  },
}));

// 在错误处理测试中，暂时禁用 MSW，使用直接的 fetch mock
beforeAll(() => {
  server.close(); // 关闭 MSW server
  global.fetch = mockFetch as typeof fetch;
});

afterAll(() => {
  // 测试结束后，恢复 MSW（为其他测试）
  server.listen({ onUnhandledRequest: 'bypass' });
});

describe('API Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTokens();
    // 确保使用 mock fetch
    global.fetch = mockFetch as typeof fetch;
  });

  describe('403 Forbidden 错误', () => {
    it('应该正确处理 403 错误', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Permission denied' }),
      });

      await expect(apiGet('/test', { skipTenantId: true })).rejects.toThrow('Permission denied');
    });
  });

  describe('404 Not Found 错误', () => {
    it('应该正确处理 404 错误', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Resource not found' }),
      });

      await expect(apiGet('/test', { skipTenantId: true })).rejects.toThrow('Resource not found');
    });
  });

  describe('500 Server Error', () => {
    it('应该正确处理 500 错误', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Internal server error' }),
      });

      await expect(apiGet('/test', { skipTenantId: true })).rejects.toThrow('Internal server error');
    });
  });

  describe('网络错误', () => {
    it('应该正确处理网络错误', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(apiGet('/test', { skipTenantId: true })).rejects.toThrow('Network error');
    });
  });

  describe('422 字段错误', () => {
    it('兼容标准 envelope 中的 FastAPI loc/msg details', async () => {
      setTokens('test-token', 'refresh-token');
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: false,
          error: {
            message: '请求数据验证失败',
            details: [{ loc: ['body', 'name'], msg: 'String should have at least 2 characters' }],
          },
        }),
      });

      const error = await apiGet('/test', { skipTenantId: true }).catch((caught) => caught);
      expect(error).toBeInstanceOf(ApiRequestError);
      if (!(error instanceof ApiRequestError)) {
        throw new Error('Expected ApiRequestError');
      }
      expect(error.status).toBe(422);
      expect(error.fieldErrors).toEqual({ name: 'String should have at least 2 characters' });
    });

    it('解析真实 backend field/path/message/type details', async () => {
      setTokens('test-token', 'refresh-token');
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: false,
          error: {
            message: '请求数据验证失败',
            details: [
              {
                field: 'tenant.max_users',
                path: ['body', 'tenant', 'max_users'],
                message: 'Input should be less than or equal to 10000000',
                type: 'less_than_equal',
              },
              {
                field: 'admin.username',
                path: ['body', 'admin', 'username'],
                message: 'String should match pattern',
                type: 'string_pattern_mismatch',
              },
            ],
          },
          detail: 'legacy detail must not override the envelope',
        }),
      });

      const error = await apiGet('/test', { skipTenantId: true }).catch((caught) => caught);
      expect(error).toBeInstanceOf(ApiRequestError);
      if (!(error instanceof ApiRequestError)) throw new Error('Expected ApiRequestError');
      expect(error.message).toBe('请求数据验证失败');
      expect(error.fieldErrors).toEqual({
        'tenant.max_users': 'Input should be less than or equal to 10000000',
        'admin.username': 'String should match pattern',
      });
    });
  });

  describe('非 JSON 响应', () => {
    it('应该正确处理非 JSON 响应', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: async () => 'Plain text response',
        json: async () => { throw new Error('Not JSON'); },
      });

      const result = await apiGet('/test', { skipTenantId: true });
      expect(result).toBe('Plain text response');
    });
  });

  describe('无错误详情响应', () => {
    it('应该使用 statusText 作为错误消息', async () => {
      setTokens('test-token', 'refresh-token');
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'text/plain' }),
        json: async () => { throw new Error('Not JSON'); },
      });

      // 实际代码中，如果 response.json() 失败，会使用 statusText 作为 detail
      // 然后对于 500 错误，如果 errorData.detail 存在，会使用它；否则使用 'Server error'
      // 由于我们提供了 statusText，它会作为 detail 使用
      await expect(apiGet('/test', { skipTenantId: true })).rejects.toThrow(/Internal Server Error|An error occurred/);
    });
  });
});
