jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => {
      const client = jest.fn();
      return Object.assign(client, {
        interceptors: {
          request: { use: jest.fn() },
          response: { use: jest.fn() },
        },
      });
    }),
    post: jest.fn(),
    isAxiosError: jest.fn(),
  },
}));

jest.mock('../../utils/tokenManager', () => ({
  getAccessToken: jest.fn(),
  getRefreshToken: jest.fn(),
  saveTokens: jest.fn(),
  clearTokens: jest.fn(),
  isTokenExpiringSoon: jest.fn(),
}));

jest.mock('../../navigation/navigationRef', () => ({
  navigateToLogin: jest.fn(),
}));

jest.mock('../../i18n', () => ({
  getT: () => ({
    common: {
      requestFailed: 'Request failed',
      networkError: 'Network error',
      unexpectedError: 'Unexpected error',
    },
  }),
}));

import { API_ENDPOINTS } from '../../constants/config';
import {
  clearTokens,
  getRefreshToken,
} from '../../utils/tokenManager';
import axios from 'axios';
import { navigateToLogin } from '../../navigation/navigationRef';
import { configureSessionInvalidationHandler } from '../client';

const mockAxiosPost = jest.mocked(axios.post);
const mockApiClient = jest.mocked(axios.create).mock.results[0].value as unknown as {
  interceptors: {
    request: { use: jest.Mock };
    response: { use: jest.Mock };
  };
};
const mockResponseUse = mockApiClient.interceptors.response.use;
const mockNavigateToLogin = jest.mocked(navigateToLogin);
const mockClearTokens = jest.mocked(clearTokens);
const mockGetRefreshToken = jest.mocked(getRefreshToken);

type ResponseErrorHandler = (error: {
  config: { url: string; headers: Record<string, string>; _retry?: boolean };
  response: { status: number };
}) => Promise<unknown>;

const getResponseErrorHandler = (): ResponseErrorHandler =>
  mockResponseUse.mock.calls[0][1] as ResponseErrorHandler;

const protected401 = (url: string) => ({
  config: { url, headers: {} },
  response: { status: 401 },
});

describe('API client expired-session handling', () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    mockAxiosPost.mockReset();
    mockClearTokens.mockClear();
    mockGetRefreshToken.mockReset();
    mockNavigateToLogin.mockClear();
    mockGetRefreshToken.mockResolvedValue('refresh-token');
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('releases every concurrent 401 waiter and invalidates the session once when refresh fails', async () => {
    let rejectRefresh!: (reason: Error) => void;
    mockAxiosPost.mockReturnValue(new Promise((_resolve, reject) => {
      rejectRefresh = reject;
    }));
    const onInvalidate = jest.fn();
    configureSessionInvalidationHandler(onInvalidate);
    const handleResponseError = getResponseErrorHandler();

    const first = handleResponseError(protected401('/api/v1/app/wallet'));
    await Promise.resolve();
    const second = handleResponseError(protected401('/api/v1/app/transactions'));
    rejectRefresh(new Error('refresh rejected'));

    const results = await Promise.allSettled([first, second]);

    expect(results.map((result) => result.status)).toEqual(['rejected', 'rejected']);
    expect(mockClearTokens).toHaveBeenCalledTimes(1);
    expect(onInvalidate).toHaveBeenCalledTimes(1);
    expect(mockNavigateToLogin).toHaveBeenCalledTimes(1);

    await expect(
      handleResponseError(protected401('/api/v1/app/charging/active'))
    ).rejects.toBeDefined();
    expect(onInvalidate).toHaveBeenCalledTimes(1);
    expect(mockNavigateToLogin).toHaveBeenCalledTimes(1);
  });

  it('returns a login 401 without refresh, global invalidation, or navigation reset', async () => {
    const onInvalidate = jest.fn();
    configureSessionInvalidationHandler(onInvalidate);
    const handleResponseError = getResponseErrorHandler();
    const loginError = protected401(API_ENDPOINTS.AUTH.LOGIN_EMAIL);

    await expect(handleResponseError(loginError)).rejects.toBe(loginError);

    expect(mockAxiosPost).not.toHaveBeenCalled();
    expect(mockClearTokens).not.toHaveBeenCalled();
    expect(onInvalidate).not.toHaveBeenCalled();
    expect(mockNavigateToLogin).not.toHaveBeenCalled();
  });
});
