import React from 'react';
import { Alert, Linking } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import MercadoPagoPaymentScreen from '../MercadoPagoPaymentScreen';
import { en as mockEn } from '../../../i18n/en';
import { startCheckoutSession } from '../../../features/payment/checkoutCoordinator';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ goBack: jest.fn() }),
  useRoute: () => ({ params: { amount: 50000, type: 'top_up' } }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn }),
}));

jest.mock('../../../components/ui/Icon', () => () => null);

jest.mock('../../../api/payments', () => ({
  formatWalletTopUpAmount: (amount: number) => amount.toFixed(2),
  isServerCheckoutUrl: () => true,
}));

jest.mock('../../../features/payment/checkoutCoordinator', () => ({
  startCheckoutSession: jest.fn(),
}));

const mockedStartCheckout = startCheckoutSession as jest.MockedFunction<typeof startCheckoutSession>;

const checkoutSession = {
  checkout_session_id: 'checkout-wallet-1',
  checkout_url: 'https://api.eslatin.com.co/api/v1/app/payments/checkout/signed-token',
  expires_at: '2026-08-09T18:30:00Z',
  purpose: 'wallet_top_up' as const,
};

describe('MercadoPagoPaymentScreen wallet top-up', () => {
  const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue(true);
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);

  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterAll(() => {
    openURL.mockRestore();
    alert.mockRestore();
  });

  it('creates wallet_top_up with a decimal amount and disables duplicate opening', async () => {
    let resolveCheckout!: (value: typeof checkoutSession) => void;
    mockedStartCheckout.mockReturnValueOnce(new Promise((resolve) => {
      resolveCheckout = resolve;
    }));

    const screen = render(<MercadoPagoPaymentScreen />);
    const openingButton = await screen.findByRole('button', { name: mockEn.payment.opening });
    expect(openingButton).toBeDisabled();

    resolveCheckout(checkoutSession);
    await waitFor(() => expect(openURL).toHaveBeenCalledWith(checkoutSession.checkout_url));
    expect(mockedStartCheckout).toHaveBeenCalledWith({
      purpose: 'wallet_top_up',
      payment_method_mode: 'new_card',
      save_card: false,
      amount: '50000.00',
      currency: 'COP',
    });
  });

  it('shows a recoverable error and allows a manual retry', async () => {
    mockedStartCheckout
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(checkoutSession);

    const screen = render(<MercadoPagoPaymentScreen />);
    await waitFor(() => expect(alert).toHaveBeenCalledWith(mockEn.common.error, mockEn.payment.openFailed));

    const retryButton = screen.getByRole('button', { name: mockEn.payment.continueToSecurePage });
    expect(retryButton).not.toBeDisabled();
    fireEvent.press(retryButton);
    await waitFor(() => expect(mockedStartCheckout).toHaveBeenCalledTimes(2));
  });
});
