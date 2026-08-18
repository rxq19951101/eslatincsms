jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

import {
  createSaveCardCheckoutSession,
  deletePaymentMethodRemote,
  getPaymentMethodTypeLabelKey,
  isSecureCheckoutUrl,
  listPaymentMethods,
  setPaymentMethodDefault,
} from '../payments';
import apiClient from '../client';

jest.mock('../client', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    post: jest.fn(),
  },
  handleApiError: jest.fn(),
}));

const mockedClient = apiClient as unknown as {
  get: jest.Mock;
  patch: jest.Mock;
  delete: jest.Mock;
  post: jest.Mock;
};

describe('PAY-MP-001 payment-method adapter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('reads only the canonical server projection', async () => {
    const items = [{
      id: 'pm-1',
      provider: 'mercadopago',
      brand: 'visa',
      payment_type: 'credit_card',
      last_four: '4242',
      is_default: true,
    }];
    mockedClient.get.mockResolvedValue({ data: { items } });

    await expect(listPaymentMethods()).resolves.toEqual(items);
    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/payment-methods');
  });

  it.each([
    ['credit_card', 'creditCard'],
    ['debit_card', 'debitCard'],
    ['prepaid_card', 'prepaidCard'],
    [null, 'bankCard'],
    ['provider_future_type', 'bankCard'],
  ] as const)('maps payment type %p without guessing credit', (paymentType, expectedKey) => {
    expect(getPaymentMethodTypeLabelKey(paymentType)).toBe(expectedKey);
  });

  it('uses the frozen default-card contract and idempotency header', async () => {
    const item = {
      id: 'pm-1',
      provider: 'mercadopago',
      brand: 'visa',
      payment_type: 'debit_card',
      last_four: '1111',
      is_default: true,
    };
    mockedClient.patch.mockResolvedValue({ data: item });

    await expect(setPaymentMethodDefault('pm-1')).resolves.toEqual(item);
    expect(mockedClient.patch).toHaveBeenCalledWith(
      '/api/v1/app/payment-methods/pm-1',
      { is_default: true },
      { headers: { 'Idempotency-Key': expect.stringMatching(/^[0-9a-f-]{36}$/) } },
    );
  });

  it('treats a delete 404 as an already-completed removal', async () => {
    mockedClient.delete.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    });

    await expect(deletePaymentMethodRemote('pm-1')).resolves.toBeUndefined();
    expect(mockedClient.delete).toHaveBeenCalledWith(
      '/api/v1/app/payment-methods/pm-1',
      { headers: { 'Idempotency-Key': expect.stringMatching(/^[0-9a-f-]{36}$/) } },
    );
  });

  it('creates a save-card hosted session without card data or amount', async () => {
    mockedClient.post.mockResolvedValue({
      data: {
        checkout_session_id: 'checkout-1',
        checkout_url: 'https://api.eslatin.com.co/checkout/checkout-1',
        expires_at: '2026-08-09T18:30:00Z',
        purpose: 'save_card',
      },
    });

    await createSaveCardCheckoutSession();

    const [, payload] = mockedClient.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload).toEqual(expect.objectContaining({
      purpose: 'save_card',
      payment_method_mode: 'new_card',
      save_card: true,
      currency: 'COP',
      return_url: 'eslatin://payment-return',
      idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/),
    }));
    expect(payload).not.toHaveProperty('amount');
    expect(payload).not.toHaveProperty('card_number');
    expect(payload).not.toHaveProperty('cvc');
  });

  it('accepts only HTTPS hosted checkout URLs', () => {
    expect(isSecureCheckoutUrl('https://api.eslatin.com.co/checkout/x')).toBe(true);
    expect(isSecureCheckoutUrl('http://api.eslatin.com.co/checkout/x')).toBe(false);
    expect(isSecureCheckoutUrl('not-a-url')).toBe(false);
  });
});
