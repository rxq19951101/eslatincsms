jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('../../../api/payments', () => ({
  classifyCheckoutQueryError: (error: {
    response?: { status?: number; data?: { detail?: { code?: string } } };
  }) => {
    const status = error.response?.status;
    const code = error.response?.data?.detail?.code;
    if (status === 404 || code === 'CHECKOUT_SESSION_NOT_FOUND') return 'expired_or_missing';
    if (status === 409 || code === 'CHECKOUT_ALREADY_CONFIRMED') return 'already_submitted';
    if (status === 503 || code === 'CHECKOUT_UNAVAILABLE') return 'temporarily_unavailable';
    return 'network_unknown';
  },
  createCheckoutSession: jest.fn(),
  getCheckoutSession: jest.fn(),
}));

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createCheckoutSession, getCheckoutSession } from '../../../api/payments';
import {
  clearPendingCheckoutSession,
  getPendingCheckoutSession,
  resolveCheckoutSession,
  startCheckoutSession,
} from '../checkoutCoordinator';

const mockedCreate = createCheckoutSession as jest.MockedFunction<typeof createCheckoutSession>;
const mockedGet = getCheckoutSession as jest.MockedFunction<typeof getCheckoutSession>;

describe('hosted checkout recovery coordinator', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await AsyncStorage.clear();
  });

  it('persists only a non-sensitive session reference for app restart recovery', async () => {
    mockedCreate.mockResolvedValue({
      checkout_session_id: 'checkout-1',
      checkout_url: 'https://api.eslatin.com.co/checkout/token',
      expires_at: '2026-08-09T18:30:00Z',
      purpose: 'save_card',
    });

    await startCheckoutSession({
      purpose: 'save_card',
      payment_method_mode: 'new_card',
      save_card: true,
    });

    await expect(getPendingCheckoutSession()).resolves.toEqual({
      checkoutSessionId: 'checkout-1',
      purpose: 'save_card',
      expiresAt: '2026-08-09T18:30:00Z',
      source: 'add_payment',
    });
    const stored = await AsyncStorage.getItem('@eslatin/payment_checkout_recovery');
    expect(stored).toContain('checkout-1');
    expect(stored).not.toContain('https://');
  });

  it('clears the recovery reference only after the server reports a terminal state', async () => {
    await AsyncStorage.setItem('@eslatin/payment_checkout_recovery', JSON.stringify({
      checkoutSessionId: 'checkout-1',
      purpose: 'wallet_top_up',
      expiresAt: '2026-08-09T18:30:00Z',
    }));
    mockedGet.mockResolvedValue({
      id: 'checkout-1',
      purpose: 'wallet_top_up',
      status: 'approved',
      next_action: null,
      expires_at: '2026-08-09T18:30:00Z',
    });

    await expect(resolveCheckoutSession('checkout-1')).resolves.toEqual(expect.objectContaining({
      kind: 'resolved',
      session: expect.objectContaining({ status: 'approved' }),
    }));

    await expect(getPendingCheckoutSession()).resolves.toBeNull();
  });

  it('clears an expired or missing reference after a 404', async () => {
    await AsyncStorage.setItem('@eslatin/payment_checkout_recovery', JSON.stringify({
      checkoutSessionId: 'checkout-expired',
      purpose: 'charging_direct',
      expiresAt: '2026-08-09T18:30:00Z',
    }));
    mockedGet.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { detail: { code: 'CHECKOUT_SESSION_NOT_FOUND' } } },
    });

    await expect(resolveCheckoutSession('checkout-expired')).resolves.toEqual({
      kind: 'expired_or_missing',
      session: null,
      purpose: 'charging_direct',
      source: 'charging_direct',
    });
    await expect(getPendingCheckoutSession()).resolves.toBeNull();
  });

  it('handles 409 with one read-only follow-up and never creates a new checkout', async () => {
    await AsyncStorage.setItem('@eslatin/payment_checkout_recovery', JSON.stringify({
      checkoutSessionId: 'checkout-submitted',
      purpose: 'charging_direct',
      expiresAt: '2026-08-09T18:30:00Z',
    }));
    mockedGet
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 409, data: { detail: { code: 'CHECKOUT_ALREADY_CONFIRMED' } } },
      })
      .mockResolvedValueOnce({
        id: 'checkout-submitted',
        purpose: 'charging_direct',
        status: 'ready',
        payment_intent_id: 'intent-1',
        next_action: null,
        expires_at: '2026-08-09T18:30:00Z',
      });

    await expect(resolveCheckoutSession('checkout-submitted')).resolves.toEqual(expect.objectContaining({
      kind: 'resolved',
      session: expect.objectContaining({ payment_intent_id: 'intent-1' }),
    }));
    expect(mockedGet).toHaveBeenCalledTimes(2);
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it.each([
    [503, 'CHECKOUT_UNAVAILABLE', 'temporarily_unavailable'],
    [undefined, undefined, 'network_unknown'],
  ] as const)('retains the original reference for recoverable query failures', async (status, code, kind) => {
    await AsyncStorage.setItem('@eslatin/payment_checkout_recovery', JSON.stringify({
      checkoutSessionId: 'checkout-retry',
      purpose: 'wallet_top_up',
      expiresAt: '2026-08-09T18:30:00Z',
    }));
    mockedGet.mockRejectedValue({
      isAxiosError: true,
      ...(status ? { response: { status, data: { detail: { code } } } } : { request: {} }),
    });

    await expect(resolveCheckoutSession('checkout-retry')).resolves.toEqual(expect.objectContaining({
      kind,
      session: null,
    }));
    await expect(getPendingCheckoutSession()).resolves.toEqual(expect.objectContaining({
      checkoutSessionId: 'checkout-retry',
      source: 'wallet_top_up',
    }));
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it('deduplicates simultaneous deep-link, foreground and polling queries', async () => {
    let resolveQuery!: (value: Awaited<ReturnType<typeof getCheckoutSession>>) => void;
    mockedGet.mockReturnValue(new Promise((resolve) => {
      resolveQuery = resolve;
    }));

    const first = resolveCheckoutSession('checkout-shared');
    const second = resolveCheckoutSession('checkout-shared');
    expect(second).toBe(first);

    resolveQuery({
      id: 'checkout-shared',
      purpose: 'save_card',
      status: 'processing',
      next_action: null,
      expires_at: '2026-08-09T18:30:00Z',
    });
    await expect(first).resolves.toEqual(expect.objectContaining({ kind: 'resolved' }));
    expect(mockedGet).toHaveBeenCalledTimes(1);
  });

  it('can explicitly clear an abandoned checkout reference', async () => {
    await AsyncStorage.setItem('@eslatin/payment_checkout_recovery', '{}');
    await clearPendingCheckoutSession();
    await expect(AsyncStorage.getItem('@eslatin/payment_checkout_recovery')).resolves.toBeNull();
  });
});
