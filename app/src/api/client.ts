/**
 * API客户端配置
 * 配置Axios实例，包含Token拦截器和刷新逻辑
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, API_ENDPOINTS } from '../constants/config';
import { getAccessToken, getRefreshToken, saveTokens, clearTokens, isTokenExpiringSoon } from '../utils/tokenManager';
import type { ApiError, AuthTokens } from '../types';
import { Platform } from 'react-native';

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
      throw new Error('No refresh token available');
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
    throw error;
  }
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
      if (originalRequest.url?.includes(API_ENDPOINTS.AUTH.REFRESH)) {
        await clearTokens();
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
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        processQueue(null, newToken);
        isRefreshing = false;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        isRefreshing = false;
        // Token刷新失败，清除Token并跳转登录
        await clearTokens();
        // TODO: 导航到登录页面
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
      return {
        message: axiosError.response.data?.message || 'An error occurred',
        code: axiosError.response.data?.code,
        details: axiosError.response.data?.details,
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
