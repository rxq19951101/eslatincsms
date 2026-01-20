/**
 * 认证相关API接口
 */

import apiClient, { handleApiError } from './client';
import { API_ENDPOINTS } from '../constants/config';
import { saveTokens, saveUserInfo } from '../utils/tokenManager';
import type { LoginResponse, User, ApiError } from '../types';

/**
 * 邮箱注册
 */
export const registerWithEmail = async (data: {
  email: string;
  password: string;
  full_name: string;
}): Promise<{ success: boolean; message: string; user_id: string }> => {
  try {
    const response = await apiClient.post(API_ENDPOINTS.AUTH.REGISTER_EMAIL, {
      ...data,
    });
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 邮箱登录
 */
export const loginWithEmail = async (data: {
  email: string;
  password: string;
  remember_me?: boolean;
}): Promise<LoginResponse> => {
  try {
    // 不再强制发送 tenant_id，后端会通过邮箱自动查找租户
    const response = await apiClient.post<LoginResponse>(
      API_ENDPOINTS.AUTH.LOGIN_EMAIL,
      data
    );

    const { access_token, refresh_token, user } = response.data;

    // 保存Token和用户信息
    await saveTokens({ access_token, refresh_token, token_type: 'bearer' });
    await saveUserInfo(user);

    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 验证邮箱
 */
export const verifyEmail = async (token: string): Promise<{ success: boolean; message: string }> => {
  try {
    const response = await apiClient.get(`${API_ENDPOINTS.AUTH.VERIFY_EMAIL}?token=${token}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 重新发送验证邮件
 */
export const resendVerificationEmail = async (email: string): Promise<{ success: boolean; message: string }> => {
  try {
    const response = await apiClient.post(API_ENDPOINTS.AUTH.RESEND_VERIFICATION, { email });
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 发送重置密码邮件
 */
export const sendResetPasswordEmail = async (email: string): Promise<{ success: boolean; message: string }> => {
  try {
    const response = await apiClient.post(API_ENDPOINTS.AUTH.RESET_PASSWORD, { email });
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 确认重置密码
 */
export const confirmResetPassword = async (data: {
  token: string;
  new_password: string;
}): Promise<{ success: boolean; message: string }> => {
  try {
    const response = await apiClient.post(API_ENDPOINTS.AUTH.CONFIRM_RESET_PASSWORD, data);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 社交登录
 */
export const loginWithSocial = async (data: {
  provider: 'google' | 'apple' | 'facebook';
  token: string;
}): Promise<LoginResponse & { is_new_user: boolean }> => {
  try {
    const response = await apiClient.post<LoginResponse & { is_new_user: boolean }>(
      `${API_ENDPOINTS.AUTH.SOCIAL_LOGIN}/${data.provider}`,
      {
        token: data.token,
      }
    );

    const { access_token, refresh_token, user } = response.data;

    // 保存Token和用户信息
    await saveTokens({ access_token, refresh_token, token_type: 'bearer' });
    await saveUserInfo(user);

    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 获取当前用户信息
 */
export const getCurrentUser = async (): Promise<User> => {
  try {
    const response = await apiClient.get<User>(API_ENDPOINTS.AUTH.ME);
    await saveUserInfo(response.data);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
};

/**
 * 登出
 */
export const logout = async (): Promise<void> => {
  try {
    await apiClient.post(API_ENDPOINTS.AUTH.LOGOUT);
  } catch (error) {
    console.error('Logout error:', error);
    // 即使API调用失败，也要清除本地Token
  }
};
