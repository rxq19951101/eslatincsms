import React from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { render, waitFor } from '@testing-library/react-native';
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
});
