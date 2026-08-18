jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

import {
  classifyCheckoutQueryError,
  createCheckoutSession,
  createWalletTopUpCheckoutSession,
  formatWalletTopUpAmount,
  getCheckoutSession,
  isAllowedMercadoPagoActionUrl,
  isServerCheckoutUrl,
  normalizePaymentReturnStatus,
} from '../payments';
import apiClient from '../client';

jest.mock('../client', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

const mockedClient = apiClient as unknown as {
  get: jest.Mock;
  post: jest.Mock;
};

describe('PAY-MP-001 hosted checkout adapter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('creates a hosted checkout with no card fields or provider credentials', async () => {
    mockedClient.post.mockResolvedValue({
      data: {
        checkout_session_id: 'checkout-1',
        checkout_url: 'https://api.eslatin.com.co/api/v1/app/payments/checkout/token',
        expires_at: '2026-08-09T18:30:00Z',
        purpose: 'wallet_top_up',
      },
    });

    await createCheckoutSession({
      purpose: 'wallet_top_up',
      payment_method_mode: 'new_card',
      save_card: false,
      amount: '50000.00',
      currency: 'COP',
    });

    const [, payload] = mockedClient.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload).toEqual(expect.objectContaining({
      purpose: 'wallet_top_up',
      amount: '50000.00',
      return_url: 'eslatin://payment-return',
      idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/),
    }));
    expect(payload).not.toHaveProperty('card_number');
    expect(payload).not.toHaveProperty('cvc');
    expect(payload).not.toHaveProperty('token');
  });

  it('removes an untrusted action URL before it reaches the UI', async () => {
    mockedClient.get.mockResolvedValue({
      data: {
        id: 'checkout-1',
        purpose: 'wallet_top_up',
        status: 'action_required',
        next_action: { type: 'open_url', url: 'https://evil.example/steal' },
        expires_at: '2026-08-09T18:30:00Z',
      },
    });

    await expect(getCheckoutSession('checkout-1')).resolves.toEqual(expect.objectContaining({
      status: 'action_required',
      next_action: null,
    }));
  });

  it('formats COP top-up amounts as decimal strings and rejects invalid boundaries', async () => {
    expect(formatWalletTopUpAmount(50000)).toBe('50000.00');
    expect(formatWalletTopUpAmount(0.1)).toBe('0.10');
    expect(() => formatWalletTopUpAmount(0)).toThrow('invalid_top_up_amount');
    expect(() => formatWalletTopUpAmount(Number.NaN)).toThrow('invalid_top_up_amount');

    mockedClient.post.mockResolvedValue({
      data: {
        checkout_session_id: 'checkout-top-up',
        checkout_url: 'https://api.eslatin.com.co/api/v1/app/payments/checkout/token',
        expires_at: '2026-08-09T18:30:00Z',
        purpose: 'wallet_top_up',
      },
    });
    await createWalletTopUpCheckoutSession('50000.00');
    expect(mockedClient.post.mock.calls[0][1]).toEqual(expect.objectContaining({
      purpose: 'wallet_top_up',
      amount: '50000.00',
    }));
    await expect(createWalletTopUpCheckoutSession('0')).rejects.toThrow('invalid_top_up_amount');
    expect(mockedClient.post).toHaveBeenCalledTimes(1);
  });

  it('allows only HTTPS Mercado Pago hosts for 3DS', () => {
    expect(isAllowedMercadoPagoActionUrl('https://www.mercadopago.com.co/verify')).toBe(true);
    expect(isAllowedMercadoPagoActionUrl('https://mercadopago.com.evil.example/verify')).toBe(false);
    expect(isAllowedMercadoPagoActionUrl('http://www.mercadopago.com.co/verify')).toBe(false);
    expect(normalizePaymentReturnStatus('approved')).toBe('approved');
    expect(normalizePaymentReturnStatus('provider_secret')).toBeUndefined();
  });

  it('allows loopback HTTP only for the local hosted-checkout sandbox', () => {
    expect(isServerCheckoutUrl('http://localhost:9000/api/v1/app/payments/checkout/token')).toBe(true);
    expect(isServerCheckoutUrl('http://127.0.0.1:9000/api/v1/app/payments/checkout/token')).toBe(false);
    expect(isServerCheckoutUrl('http://api.eslatin.com.co/api/v1/app/payments/checkout/token')).toBe(false);
  });

  it.each([
    [404, 'CHECKOUT_SESSION_NOT_FOUND', 'expired_or_missing'],
    [409, 'CHECKOUT_ALREADY_CONFIRMED', 'already_submitted'],
    [503, 'CHECKOUT_UNAVAILABLE', 'temporarily_unavailable'],
    [500, 'INTERNAL_ERROR', 'network_unknown'],
  ] as const)('classifies checkout query HTTP %s safely', (status, code, expected) => {
    expect(classifyCheckoutQueryError({
      isAxiosError: true,
      response: { status, data: { detail: { code, message: 'provider text must not escape' } } },
    })).toBe(expected);
  });

  it('keeps network failures in an unknown state', () => {
    expect(classifyCheckoutQueryError({ isAxiosError: true, request: {} })).toBe('network_unknown');
    expect(classifyCheckoutQueryError(new Error('offline'))).toBe('network_unknown');
  });
});
