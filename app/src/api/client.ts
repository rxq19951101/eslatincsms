/**
 * API客户端配置
 * 配置Axios实例，包含Token拦截器和刷新逻辑
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, API_ENDPOINTS } from '../constants/config';
import { getAccessToken, getRefreshToken, saveTokens, clearTokens, isTokenExpiringSoon } from '../utils/tokenManager';
import type { ApiError, AuthTokens } from '../types';
import { Platform } from 'react-native';
import { navigateToLogin } from '../navigation/navigationRef';
import { getT } from '../i18n';

// 创建Axios实例
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 标记是否正在刷新Token
let isRefreshing = false;
// 存储等待刷新的请求队列
let failedQueue: Array<{
  resolve: (value: any) => void;
  reject: (reason: any) => void;
}> = [];
let sessionInvalidationHandler: (() => void) | null = null;
let sessionInvalidationPromise: Promise<void> | null = null;
let isSessionInvalidated = false;
let hasResetNavigation = false;

export const configureSessionInvalidationHandler = (handler: () => void) => {
  sessionInvalidationHandler = handler;
};

const markSessionActive = () => {
  isSessionInvalidated = false;
  hasResetNavigation = false;
};

const invalidateLocalSession = async (): Promise<void> => {
  if (isSessionInvalidated) {
    await sessionInvalidationPromise;
    return;
  }

  isSessionInvalidated = true;
  sessionInvalidationPromise = (async () => {
    await clearTokens();
    sessionInvalidationHandler?.();
    if (!hasResetNavigation) {
      hasResetNavigation = true;
      navigateToLogin();
    }
  })();

  try {
    await sessionInvalidationPromise;
  } finally {
    sessionInvalidationPromise = null;
  }
};

/**
 * 处理队列中的请求
 */
const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

/**
 * 刷新访问Token
 */
export const refreshAccessToken = async (): Promise<string | null> => {
  try {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) {
      return null;
    }

    const response = await axios.post<AuthTokens>(
      `${API_BASE_URL}${API_ENDPOINTS.AUTH.REFRESH}`,
      { refresh_token: refreshToken }
    );

    const { access_token, refresh_token: new_refresh_token } = response.data;
    
    await saveTokens({
      access_token,
      refresh_token: new_refresh_token,
      token_type: 'bearer',
    });

    markSessionActive();
    return access_token;
  } catch (error) {
    console.error('Token refresh failed:', error);
    return null;
  }
};

const shouldSkipTokenRefresh = (url?: string): boolean => {
  if (!url) return false;
  const skipUrls = [
    API_ENDPOINTS.AUTH.LOGIN_EMAIL,
    API_ENDPOINTS.AUTH.REGISTER_EMAIL,
    API_ENDPOINTS.AUTH.SOCIAL_LOGIN,
    API_ENDPOINTS.AUTH.RESET_PASSWORD,
    API_ENDPOINTS.AUTH.CONFIRM_RESET_PASSWORD,
    API_ENDPOINTS.AUTH.VERIFY_EMAIL,
    API_ENDPOINTS.AUTH.RESEND_VERIFICATION,
    API_ENDPOINTS.AUTH.REFRESH,
    API_ENDPOINTS.AUTH.LOGOUT,
  ];
  return skipUrls.some((u) => url.includes(u));
};

const shouldMarkSessionActive = (url?: string): boolean => {
  if (!url) return false;
  return [
    API_ENDPOINTS.AUTH.LOGIN_EMAIL,
    API_ENDPOINTS.AUTH.SOCIAL_LOGIN,
    API_ENDPOINTS.AUTH.VERIFY_EMAIL,
  ].some((endpoint) => url.includes(endpoint));
};

/**
 * 请求拦截器
 * 自动添加Token，检查Token是否即将过期
 */
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // 跳过登录和注册等不需要token的请求
    const skipAuthUrls = [
      API_ENDPOINTS.AUTH.LOGIN_EMAIL,
      API_ENDPOINTS.AUTH.REGISTER_EMAIL,
      API_ENDPOINTS.AUTH.SOCIAL_LOGIN,
      API_ENDPOINTS.AUTH.RESET_PASSWORD,
      API_ENDPOINTS.AUTH.CONFIRM_RESET_PASSWORD,
      API_ENDPOINTS.AUTH.VERIFY_EMAIL,
      API_ENDPOINTS.AUTH.RESEND_VERIFICATION,
    ];
    
    const isAuthRequest = skipAuthUrls.some(url => config.url?.includes(url));
    
    if (isAuthRequest) {
      // 认证请求不需要添加token
      return config;
    }

    // 获取访问Token
    const accessToken = await getAccessToken();

    if (accessToken) {
      // Web 端不做“预刷新”，只在遇到 401 时再刷新（避免本地存储/时钟差异导致循环 refresh 401）
      if (Platform.OS !== 'web' && isTokenExpiringSoon(accessToken) && !isRefreshing) {
        const refreshToken = await getRefreshToken();
        // 没有 refresh_token 就别尝试刷新
        if (refreshToken) {
          isRefreshing = true;
          try {
            const newToken = await refreshAccessToken();
            if (newToken) {
              config.headers.Authorization = `Bearer ${newToken}`;
              processQueue(null, newToken);
            } else {
              const refreshError = new Error('Unable to refresh access token');
              processQueue(refreshError, null);
              await invalidateLocalSession();
            }
          } catch (error) {
            processQueue(error as Error, null);
            await invalidateLocalSession();
          } finally {
            isRefreshing = false;
          }
        } else {
          config.headers.Authorization = `Bearer ${accessToken}`;
        }
      } else {
        config.headers.Authorization = `Bearer ${accessToken}`;
      }
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * 响应拦截器
 * 处理401错误，自动刷新Token
 */
apiClient.interceptors.response.use(
  (response) => {
    if (shouldMarkSessionActive(response.config?.url)) {
      markSessionActive();
    }
    return response;
  },
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // 如果是401错误且未重试过（且不是 refresh 请求本身）
    if (error.response?.status === 401 && !originalRequest._retry) {
      // 登录/注册/refresh 等接口，不应该触发 refresh（避免“没有 refresh token available”覆盖原始错误）
      if (shouldSkipTokenRefresh(originalRequest.url)) {
        return Promise.reject(error);
      }
      if (isRefreshing) {
        // 如果正在刷新Token，将请求加入队列
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => {
            return Promise.reject(err);
          });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const newToken = await refreshAccessToken();
        if (!newToken) {
          processQueue(error, null);
          await invalidateLocalSession();
          return Promise.reject(error);
        }
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        processQueue(null, newToken);
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        await invalidateLocalSession();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // 其他错误直接返回
    return Promise.reject(error);
  }
);

export default apiClient;

type ErrorDetail = {
  field?: unknown;
  path?: unknown;
  message?: unknown;
  type?: unknown;
  loc?: unknown;
  msg?: unknown;
};

function errorField(value: unknown): string | undefined {
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
}

function apiFieldErrors(details: unknown): Record<string, string> {
  if (!Array.isArray(details)) return {};
  return details.reduce<Record<string, string>>((result, issue) => {
    if (!issue || typeof issue !== 'object') return result;
    const entry = issue as ErrorDetail;
    const field = errorField(entry.field) ?? errorField(entry.path) ?? errorField(entry.loc) ?? 'form';
    const message = typeof entry.message === 'string'
      ? entry.message
      : typeof entry.msg === 'string'
        ? entry.msg
        : undefined;
    if (message && !result[field]) result[field] = message;
    return result;
  }, {});
}

/** Parse the canonical backend error envelope, retaining legacy FastAPI detail support. */
export function parseApiErrorPayload(data: unknown, status: number): ApiError {
  const body = data && typeof data === 'object' ? data as Record<string, any> : {};
  const envelope = body.error && typeof body.error === 'object' ? body.error : {};
  const details = envelope.details
    ?? body.details
    ?? (Array.isArray(body.detail) ? body.detail : undefined)
    ?? body.detail;
  let message = typeof envelope.message === 'string'
    ? envelope.message
    : typeof body.message === 'string'
      ? body.message
      : typeof body.detail === 'string'
        ? body.detail
        : undefined;

  if (!message && Array.isArray(details)) {
    const messages = details
      .map((entry: ErrorDetail) => entry?.message ?? entry?.msg)
      .filter((value: unknown): value is string => typeof value === 'string' && value.length > 0);
    if (messages.length) message = messages.join('; ');
  }

  return {
    message: message || getT().common.requestFailed,
    code: typeof envelope.code === 'string'
      ? envelope.code
      : typeof body.code === 'string'
        ? body.code
        : `HTTP_${status}`,
    status,
    details,
    fieldErrors: apiFieldErrors(details),
  };
}

/**
 * 统一的错误处理
 */
export const handleApiError = (error: any): ApiError => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    
    if (axiosError.response) {
      return parseApiErrorPayload(axiosError.response.data, axiosError.response.status);
    } else if (axiosError.request) {
      // 请求已发出但没有收到响应
      return {
        message: getT().common.networkError,
        code: 'NETWORK_ERROR',
      };
    }
  }
  
  // 其他错误
  return {
    message: error?.message || getT().common.unexpectedError,
    code: 'UNKNOWN_ERROR',
  };
};
