import { configureStore } from '@reduxjs/toolkit';
import type { User } from '../../../types';
import reducer, {
  initializeAuth,
  invalidateLocalSession,
} from '../authSlice';
import { refreshAccessToken } from '../../../api/client';
import {
  clearTokens,
  getAccessToken,
  getUserInfo,
  isTokenExpired,
} from '../../../utils/tokenManager';

jest.mock('../../../api/auth', () => ({}));
jest.mock('../../../api/client', () => ({
  refreshAccessToken: jest.fn(),
}));
jest.mock('../../../utils/tokenManager', () => ({
  clearTokens: jest.fn(),
  getAccessToken: jest.fn(),
  getUserInfo: jest.fn(),
  isTokenExpired: jest.fn(),
}));

const mockRefreshAccessToken = jest.mocked(refreshAccessToken);
const mockClearTokens = jest.mocked(clearTokens);
const mockGetAccessToken = jest.mocked(getAccessToken);
const mockGetUserInfo = jest.mocked(getUserInfo);
const mockIsTokenExpired = jest.mocked(isTokenExpired);

const cachedUser: User = {
  id: 'user-1',
  email: 'driver@example.com',
  full_name: 'Driver',
  email_verified: true,
};

const createAuthStore = () => configureStore({ reducer: { auth: reducer } });

describe('auth session initialization', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('restores a cached user when the access token is still valid', async () => {
    mockGetAccessToken.mockResolvedValue('valid-token');
    mockIsTokenExpired.mockReturnValue(false);
    mockGetUserInfo.mockResolvedValue(cachedUser);
    const store = createAuthStore();

    await store.dispatch(initializeAuth());

    expect(store.getState().auth).toMatchObject({
      user: cachedUser,
      isAuthenticated: true,
      isInitialized: true,
    });
    expect(mockRefreshAccessToken).not.toHaveBeenCalled();
    expect(mockClearTokens).not.toHaveBeenCalled();
  });

  it('refreshes an expired access token before restoring the cached user', async () => {
    mockGetAccessToken.mockResolvedValue('expired-token');
    mockIsTokenExpired.mockReturnValue(true);
    mockRefreshAccessToken.mockResolvedValue('new-access-token');
    mockGetUserInfo.mockResolvedValue(cachedUser);
    const store = createAuthStore();

    await store.dispatch(initializeAuth());

    expect(mockRefreshAccessToken).toHaveBeenCalledTimes(1);
    expect(store.getState().auth.isAuthenticated).toBe(true);
    expect(store.getState().auth.user).toEqual(cachedUser);
  });

  it('clears local auth data when an expired token cannot be refreshed', async () => {
    mockGetAccessToken.mockResolvedValue('expired-token');
    mockIsTokenExpired.mockReturnValue(true);
    mockRefreshAccessToken.mockResolvedValue(null);
    const store = createAuthStore();

    await store.dispatch(initializeAuth());

    expect(mockClearTokens).toHaveBeenCalledTimes(1);
    expect(store.getState().auth).toMatchObject({
      user: null,
      isAuthenticated: false,
      isInitialized: true,
    });
  });

  it('resets Redux auth state through the unified invalidation action', () => {
    const authenticatedState = {
      user: cachedUser,
      isAuthenticated: true,
      isLoading: true,
      error: { message: 'stale error' },
      isInitialized: true,
    };

    expect(reducer(authenticatedState, invalidateLocalSession())).toEqual({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      isInitialized: true,
    });
  });
});
