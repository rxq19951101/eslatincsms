import { API_BASE_URL } from './constants';
import { getAccessToken, getRefreshToken, setTokens, clearTokens, redirectToLogin } from './auth';
import { getTenantId } from './tenant';
import { useAuthStore } from '@/store/authStore';
import { RefreshTokenRequest, RefreshTokenResponse } from '@/types';

/**
 * API 请求配置
 */
interface RequestConfig extends RequestInit {
  skipAuth?: boolean; // 跳过认证（用于登录等接口）
  skipTenantId?: boolean; // 跳过租户 ID（用于认证接口）
  retryCount?: number; // 重试次数（内部使用）
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly fieldErrors: Record<string, string> = {}
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

function parseFieldErrors(details: unknown): Record<string, string> {
  if (!Array.isArray(details)) return {};

  const normalizePath = (value: unknown): string | undefined => {
    const parts = Array.isArray(value)
      ? value
      : typeof value === 'string'
        ? value.split('.').filter(Boolean)
        : [];
    const normalized = parts
      .filter((part): part is string | number => typeof part === 'string' || typeof part === 'number')
      .filter((part, index) => index > 0 || !['body', 'query', 'path', 'header'].includes(String(part)))
      .map(String)
      .join('.');
    return normalized || undefined;
  };

  return details.reduce<Record<string, string>>((result, issue) => {
    if (!issue || typeof issue !== 'object') return result;
    const entry = issue as {
      field?: unknown;
      path?: unknown;
      message?: unknown;
      type?: unknown;
      loc?: unknown;
      msg?: unknown;
    };
    const field = normalizePath(entry.field)
      ?? normalizePath(entry.path)
      ?? normalizePath(entry.loc)
      ?? 'form';
    const message = typeof entry.message === 'string'
      ? entry.message
      : typeof entry.msg === 'string'
        ? entry.msg
        : undefined;
    if (message && !result[field]) {
      result[field] = message;
    }
    return result;
  }, {});
}

/**
 * 刷新 access token
 */
async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/admin/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken } as RefreshTokenRequest),
    });

    if (!response.ok) {
      return false;
    }

    const data = (await response.json()) as RefreshTokenResponse;
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch (error) {
    console.error('Failed to refresh token:', error);
    return false;
  }
}

/**
 * 统一的 API 请求函数
 */
export async function apiRequest<T = any>(
  endpoint: string,
  config: RequestConfig = {}
): Promise<T> {
  const {
    skipAuth = false,
    skipTenantId = false,
    retryCount = 0,
    headers = {},
    ...restConfig
  } = config;

  // 构建完整 URL
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

  // 构建请求头（使用 Record 类型以便动态添加属性）
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(headers as Record<string, string>),
  };

  // 添加认证 Token（如果不需要跳过）
  if (!skipAuth) {
    const accessToken = getAccessToken();
    if (accessToken) {
      requestHeaders['Authorization'] = `Bearer ${accessToken}`;
    }
  }

  // 添加租户 ID（如果不需要跳过 tenant_id）
  // 注意：即使 skipAuth 为 true（如登录接口），只要 skipTenantId 为 false，也应该尝试添加 tenant_id
  if (!skipTenantId) {
    const userInfo = useAuthStore.getState().user || null;
    const tenantId = getTenantId(userInfo);
    const isSuperAdmin = userInfo?.is_super_admin || false;

    // 如果不是 super_admin 且没有 tenant_id，但已经认证（有 token），阻止请求
    if (!isSuperAdmin && !tenantId && !skipAuth) {
      // 跳转到租户选择页（如果存在）
      if (typeof window !== 'undefined') {
        const hasSelectTenantPage = false; // TODO: 实现租户选择页后改为 true
        if (hasSelectTenantPage) {
          window.location.href = '/select-tenant';
        } else {
          // 如果没有租户选择页，跳转到登录页
          redirectToLogin();
        }
      }
      throw new Error('Tenant ID required');
    }

    // 只要有 tenant_id 就带上（包括 super_admin 场景）
    // - super_admin 不带 tenant_id 表示“跨租户聚合/全局视角”
    // - 但创建/写操作通常必须明确 tenant_id，因此 super_admin 也需要可选 tenant_id
    if (tenantId) {
      requestHeaders['X-Tenant-Id'] = tenantId;
    }
  }

  try {
    // 发送请求
    const response = await fetch(url, {
      ...restConfig,
      headers: requestHeaders as HeadersInit,
    });

    // 处理 401 错误（自动刷新 token）
    if (response.status === 401 && !skipAuth && retryCount < 1) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        // 重试请求（最多重试 1 次）
        return apiRequest<T>(endpoint, {
          ...config,
          retryCount: retryCount + 1,
        });
      } else {
        // 刷新失败，清除 token，跳转登录页
        clearTokens();
        useAuthStore.getState().logout();
        redirectToLogin();
        throw new Error('Authentication failed');
      }
    }

    // 处理其他错误
    if (!response.ok) {
      let errorData: {
        success?: boolean;
        detail?: unknown;
        status_code?: number;
        message?: unknown;
        error?: { message?: unknown; details?: unknown; detail?: unknown };
      };
      try {
        errorData = await response.json();
      } catch {
        errorData = {
          detail: response.statusText || 'An error occurred',
          status_code: response.status,
        };
      }

      const envelopeMessage = typeof errorData.error?.message === 'string'
        ? errorData.error.message
        : undefined;
      const topLevelMessage = typeof errorData.message === 'string' ? errorData.message : undefined;
      const legacyDetail = typeof errorData.detail === 'string' ? errorData.detail : undefined;
      const nestedDetail = typeof errorData.error?.detail === 'string' ? errorData.error.detail : undefined;
      const validationDetails = errorData.error?.details
        ?? (Array.isArray(errorData.detail) ? errorData.detail : undefined)
        ?? (Array.isArray(errorData.error?.message) ? errorData.error.message : undefined);
      const fallback = response.status === 403
        ? 'Permission denied'
        : response.status === 404
          ? 'Resource not found'
          : response.status >= 500
            ? 'Server error'
            : 'Request failed';
      throw new ApiRequestError(
        envelopeMessage || topLevelMessage || legacyDetail || nestedDetail || fallback,
        response.status,
        parseFieldErrors(validationDetails)
      );
    }

    // 解析响应
    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      return (await response.json()) as T;
    } else {
      return (await response.text()) as T;
    }
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Network error');
  }
}

/**
 * GET 请求
 */
export function apiGet<T = any>(endpoint: string, config?: RequestConfig): Promise<T> {
  return apiRequest<T>(endpoint, { ...config, method: 'GET' });
}

/**
 * POST 请求
 */
export function apiPost<T = any>(
  endpoint: string,
  data?: unknown,
  config?: RequestConfig
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...config,
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * PUT 请求
 */
export function apiPut<T = any>(
  endpoint: string,
  data?: unknown,
  config?: RequestConfig
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...config,
    method: 'PUT',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * DELETE 请求
 */
export function apiDelete<T = any>(endpoint: string, config?: RequestConfig): Promise<T> {
  return apiRequest<T>(endpoint, { ...config, method: 'DELETE' });
}

/**
 * PATCH 请求
 */
export function apiPatch<T = any>(
  endpoint: string,
  data?: unknown,
  config?: RequestConfig
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...config,
    method: 'PATCH',
    body: data ? JSON.stringify(data) : undefined,
  });
}
