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
const refreshAccessToken = async (): Promise<string | null> => {
  try {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) {
      // 没有 refresh token：不应该在这里抛错“覆盖”原始 401
      // 交给上层（响应拦截器）决定如何处理（通常是清理本地 token 并让调用方走重新登录）
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

    return access_token;
  } catch (error) {
    console.error('Token refresh failed:', error);
    await clearTokens();
    return null;
  }
};

const shouldSkipTokenRefresh = (url?: string): boolean => {
  if (!url) return false;
  const skipUrls = [
    API_ENDPOINTS.AUTH.LOGIN_EMAIL,
    API_ENDPOINTS.AUTH.REGISTER_EMAIL,
    API_ENDPOINTS.AUTH.RESET_PASSWORD,
    API_ENDPOINTS.AUTH.CONFIRM_RESET_PASSWORD,
    API_ENDPOINTS.AUTH.VERIFY_EMAIL,
    API_ENDPOINTS.AUTH.RESEND_VERIFICATION,
    API_ENDPOINTS.AUTH.REFRESH,
    API_ENDPOINTS.AUTH.LOGOUT,
  ];
  return skipUrls.some((u) => url.includes(u));
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
            config.headers.Authorization = `Bearer ${newToken}`;
            isRefreshing = false;
            processQueue(null, newToken);
          } catch (error) {
            isRefreshing = false;
            processQueue(error as Error, null);
            await clearTokens();
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
          // 刷新失败 or 没有 refresh token：清理本地 token，并把原始 401 返回给调用方
          isRefreshing = false;
          await clearTokens();
          navigateToLogin();
          return Promise.reject(error);
        }
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        processQueue(null, newToken);
        isRefreshing = false;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        isRefreshing = false;
        // Token刷新失败，清除Token并跳转登录
        await clearTokens();
        navigateToLogin();
        return Promise.reject(refreshError);
      }
    }

    // 其他错误直接返回
    return Promise.reject(error);
  }
);

export default apiClient;

/**
 * 统一的错误处理
 */
export const handleApiError = (error: any): ApiError => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    
    if (axiosError.response) {
      // 服务器返回错误
      const status = axiosError.response.status;
      const data: any = axiosError.response.data;

      // FastAPI 常见错误字段是 detail（可能是 string / object / array）
      // 自定义异常处理器返回 { success, error: { message, code } }
      let message: string | undefined = data?.message ?? data?.error?.message;
      if (!message && data?.detail) {
        if (typeof data.detail === 'string') {
          message = data.detail;
        } else if (Array.isArray(data.detail)) {
          // 422 validation errors: [{loc, msg, type}, ...]
          const msgs = data.detail
            .map((d: any) => d?.msg || d?.message || JSON.stringify(d))
            .filter(Boolean);
          message = msgs.length ? msgs.join('; ') : 'Request validation failed';
        } else {
          message = typeof data.detail === 'object' ? JSON.stringify(data.detail) : String(data.detail);
        }
      }

      return {
        message: message || 'An error occurred',
        code: data?.code || `HTTP_${status}`,
        details: data?.details ?? data?.detail,
      };
    } else if (axiosError.request) {
      // 请求已发出但没有收到响应
      return {
        message: 'Network error. Please check your connection.',
        code: 'NETWORK_ERROR',
      };
    }
  }
  
  // 其他错误
  return {
    message: error.message || 'An unexpected error occurred',
    code: 'UNKNOWN_ERROR',
  };
};
