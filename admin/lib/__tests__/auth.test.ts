import { describe, it, expect, beforeEach } from 'vitest';
import {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  isAuthenticated,
} from '../auth';
import { STORAGE_KEYS } from '../constants';

describe('auth utilities', () => {
  beforeEach(() => {
    // 清理 localStorage
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        window.localStorage.clear();
      } catch (e) {
        Object.keys(window.localStorage).forEach(key => {
          window.localStorage.removeItem(key);
        });
      }
    }
  });

  describe('getAccessToken', () => {
    it('应该从 localStorage 读取 access_token', () => {
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, 'test-token');
      expect(getAccessToken()).toBe('test-token');
    });

    it('应该返回 null 如果没有 token', () => {
      expect(getAccessToken()).toBeNull();
    });
  });

  describe('setTokens', () => {
    it('应该存储 access_token 和 refresh_token', () => {
      setTokens('access-token', 'refresh-token');
      expect(localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)).toBe('access-token');
      expect(localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)).toBe('refresh-token');
    });
  });

  describe('clearTokens', () => {
    it('应该清除所有 token', () => {
      setTokens('access-token', 'refresh-token');
      clearTokens();
      expect(getAccessToken()).toBeNull();
      expect(getRefreshToken()).toBeNull();
    });
  });

  describe('isAuthenticated', () => {
    it('应该在有 access_token 时返回 true', () => {
      setTokens('access-token', 'refresh-token');
      expect(isAuthenticated()).toBe(true);
    });

    it('应该在无 access_token 时返回 false', () => {
      expect(isAuthenticated()).toBe(false);
    });
  });
});