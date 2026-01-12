/**
 * Token管理工具
 * 负责Token的存储、获取、刷新和清除
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../constants/config';
import type { AuthTokens, User } from '../types';

/**
 * 保存认证Token
 */
export const saveTokens = async (tokens: AuthTokens): Promise<void> => {
  try {
    await AsyncStorage.multiSet([
      [STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token],
      [STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token],
    ]);
  } catch (error) {
    console.error('Error saving tokens:', error);
    throw error;
  }
};

/**
 * 获取访问Token
 */
export const getAccessToken = async (): Promise<string | null> => {
  try {
    return await AsyncStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  } catch (error) {
    console.error('Error getting access token:', error);
    return null;
  }
};

/**
 * 获取刷新Token
 */
export const getRefreshToken = async (): Promise<string | null> => {
  try {
    return await AsyncStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
  } catch (error) {
    console.error('Error getting refresh token:', error);
    return null;
  }
};

/**
 * 清除所有Token
 */
export const clearTokens = async (): Promise<void> => {
  try {
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.ACCESS_TOKEN,
      STORAGE_KEYS.REFRESH_TOKEN,
      STORAGE_KEYS.USER_INFO,
    ]);
  } catch (error) {
    console.error('Error clearing tokens:', error);
    throw error;
  }
};

/**
 * 保存用户信息
 */
export const saveUserInfo = async (user: User): Promise<void> => {
  try {
    await AsyncStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(user));
  } catch (error) {
    console.error('Error saving user info:', error);
    throw error;
  }
};

/**
 * 获取用户信息
 */
export const getUserInfo = async (): Promise<User | null> => {
  try {
    const userStr = await AsyncStorage.getItem(STORAGE_KEYS.USER_INFO);
    return userStr ? JSON.parse(userStr) : null;
  } catch (error) {
    console.error('Error getting user info:', error);
    return null;
  }
};

/**
 * 保存"记住我"状态
 */
export const saveRememberMe = async (remember: boolean): Promise<void> => {
  try {
    await AsyncStorage.setItem(STORAGE_KEYS.REMEMBER_ME, remember.toString());
  } catch (error) {
    console.error('Error saving remember me:', error);
  }
};

/**
 * 获取"记住我"状态
 */
export const getRememberMe = async (): Promise<boolean> => {
  try {
    const remember = await AsyncStorage.getItem(STORAGE_KEYS.REMEMBER_ME);
    return remember === 'true';
  } catch (error) {
    console.error('Error getting remember me:', error);
    return false;
  }
};

/**
 * 检查是否已登录
 */
export const isAuthenticated = async (): Promise<boolean> => {
  const accessToken = await getAccessToken();
  return !!accessToken;
};

/**
 * 解析JWT Token（不验证签名，仅解析payload）
 */
export const parseJWT = (token: string): any => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch (error) {
    console.error('Error parsing JWT:', error);
    return null;
  }
};

/**
 * 检查Token是否过期
 */
export const isTokenExpired = (token: string): boolean => {
  try {
    const payload = parseJWT(token);
    if (!payload || !payload.exp) return true;
    
    const currentTime = Math.floor(Date.now() / 1000);
    return payload.exp < currentTime;
  } catch (error) {
    return true;
  }
};

/**
 * 检查Token是否即将过期（5分钟内）
 */
export const isTokenExpiringSoon = (token: string): boolean => {
  try {
    const payload = parseJWT(token);
    // 解析失败或没有 exp 时，不做“即将过期”判断，避免误触发刷新导致循环报错
    if (!payload || !payload.exp) return false;
    
    const currentTime = Math.floor(Date.now() / 1000);
    const fiveMinutes = 5 * 60;
    return payload.exp < currentTime + fiveMinutes;
  } catch (error) {
    return false;
  }
};
