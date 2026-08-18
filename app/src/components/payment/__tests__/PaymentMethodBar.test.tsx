import React from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { I18nProvider, type AppLocale } from '../../../i18n';
import { PaymentMethodBar } from '../PaymentMethodBar';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('../../ui/Icon', () => {
  const { View } = require('react-native');
  return (props: Record<string, unknown>) => <View {...props} />;
});

describe('PaymentMethodBar localization', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it.each([
    ['zh', '支付方式', '钱包余额 · 哥伦比亚比索'],
    ['en', 'Payment method', 'Wallet balance · Colombian pesos'],
    ['es', 'Método de pago', 'Saldo de billetera · Pesos colombianos'],
  ] as const)('renders all labels in %s', async (locale: AppLocale, title, balanceLabel) => {
    await AsyncStorage.setItem('@eslatin/locale', locale);
    const screen = render(
      <I18nProvider>
        <PaymentMethodBar balanceCOP={12000} onPressTopUp={() => {}} />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(title)).toBeTruthy();
      expect(screen.getByText(balanceLabel)).toBeTruthy();
    });
  });

  it('states that a new charging card is one-time and never renders a save toggle', async () => {
    await AsyncStorage.setItem('@eslatin/locale', 'en');
    const screen = render(
      <I18nProvider>
        <PaymentMethodBar
          balanceCOP={12000}
          allowDirectCard
          selectedMethod="direct_card"
        />
      </I18nProvider>
    );

    expect(await screen.findByText(/will not be saved/i)).toBeTruthy();
    expect(screen.queryByTestId('app-charging-save-card-toggle')).toBeNull();
    expect(screen.queryByTestId('app-charging-save-card-switch')).toBeNull();
  });

  it('shows prepaid type, last four, CVV hint and default status for a saved card', async () => {
    await AsyncStorage.setItem('@eslatin/locale', 'en');
    const screen = render(
      <I18nProvider>
        <PaymentMethodBar
          balanceCOP={12000}
          allowDirectCard
          selectedMethod="direct_card"
          selectedSavedPaymentMethodId="saved-card-1"
          savedPaymentMethods={[{
            id: 'saved-card-1',
            provider: 'mercadopago',
            brand: 'visa',
            payment_type: 'prepaid_card',
            last_four: '4242',
            is_default: true,
          }]}
        />
      </I18nProvider>
    );

    await screen.findByTestId('app-charging-payment-card-saved-card-1');
    expect(screen.getByText('visa · •••• 4242')).toBeTruthy();
    expect(await screen.findByText(/Prepaid card/)).toBeTruthy();
    expect(screen.getByText('Default')).toBeTruthy();
    expect(screen.queryByTestId('app-charging-save-card-switch')).toBeNull();
  });

  it('shows a generic bank-card label for a legacy null type', async () => {
    await AsyncStorage.setItem('@eslatin/locale', 'en');
    const screen = render(
      <I18nProvider>
        <PaymentMethodBar
          balanceCOP={12000}
          allowDirectCard
          selectedMethod="direct_card"
          savedPaymentMethods={[{
            id: 'legacy-card',
            provider: 'mercadopago',
            brand: null,
            payment_type: null,
            last_four: '1111',
            is_default: false,
          }]}
        />
      </I18nProvider>
    );

    expect(await screen.findByText(/Bank card/)).toBeTruthy();
    expect(screen.queryByText(/Credit card/)).toBeNull();
  });

  it('keeps the new-card option and exposes a retry when saved cards fail to load', async () => {
    await AsyncStorage.setItem('@eslatin/locale', 'en');
    const onRetry = jest.fn();
    const screen = render(
      <I18nProvider>
        <PaymentMethodBar
          balanceCOP={12000}
          allowDirectCard
          selectedMethod="direct_card"
          savedPaymentMethodsError
          onRetrySavedPaymentMethods={onRetry}
        />
      </I18nProvider>
    );

    expect(await screen.findByText('Use a new card')).toBeTruthy();
    expect(screen.getByText(/Saved cards could not be loaded/)).toBeTruthy();
    fireEvent.press(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
