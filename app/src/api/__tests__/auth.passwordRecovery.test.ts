import apiClient from '../client';
import { sendResetPasswordEmail } from '../auth';
import type { AppLocale } from '../../i18n';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('../client', () => ({
  __esModule: true,
  default: { post: jest.fn() },
  handleApiError: jest.fn((error) => error),
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('App password recovery API contract', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedClient.post.mockResolvedValue({
      data: { success: true, message: 'ok' },
    });
  });

  it.each<AppLocale>(['es', 'en', 'zh'])(
    'submits the active %s locale with the reset request',
    async (locale) => {
      await sendResetPasswordEmail('driver@example.com', locale);

      expect(mockedClient.post).toHaveBeenCalledWith(
        '/api/v1/app/auth/reset-password',
        { email: 'driver@example.com', locale }
      );
    }
  );

  it('keeps locale optional for legacy callers', async () => {
    await sendResetPasswordEmail('driver@example.com');

    expect(mockedClient.post).toHaveBeenCalledWith(
      '/api/v1/app/auth/reset-password',
      { email: 'driver@example.com' }
    );
  });
});
