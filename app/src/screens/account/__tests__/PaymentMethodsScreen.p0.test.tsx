import React from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, render, waitFor } from '@testing-library/react-native';

import PaymentMethodsScreen from '../PaymentMethodsScreen';
import { I18nProvider, type AppLocale } from '../../../i18n';
import { listPaymentMethods } from '../../../api/payments';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

let mockFocusEffect: (() => void | (() => void)) | undefined;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ goBack: jest.fn(), navigate: jest.fn() }),
  useFocusEffect: (callback: () => void | (() => void)) => {
    mockFocusEffect = callback;
  },
}));

jest.mock('../../../api/payments', () => ({
  deletePaymentMethodRemote: jest.fn(),
  getPaymentMethodTypeLabelKey: (value: unknown) => {
    if (value === 'credit_card') return 'creditCard';
    if (value === 'debit_card') return 'debitCard';
    if (value === 'prepaid_card') return 'prepaidCard';
    return 'bankCard';
  },
  listPaymentMethods: jest.fn(),
  setPaymentMethodDefault: jest.fn(),
}));

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return (props: Record<string, unknown>) => <View {...props} />;
});

const mockedListPaymentMethods = listPaymentMethods as jest.MockedFunction<typeof listPaymentMethods>;

describe('PaymentMethodsScreen P0 payment-type projection', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    mockFocusEffect = undefined;
    await AsyncStorage.clear();
    mockedListPaymentMethods.mockResolvedValue([
      {
        id: 'prepaid-1',
        provider: 'mercadopago',
        brand: 'master',
        payment_type: 'prepaid_card',
        last_four: '2222',
        is_default: true,
      },
      {
        id: 'legacy-1',
        provider: 'mercadopago',
        brand: null,
        payment_type: null,
        last_four: '1111',
        is_default: false,
      },
    ]);
  });

  it.each([
    ['es', 'Tarjeta prepagada', 'Tarjeta bancaria', 'Predeterminado'],
    ['en', 'Prepaid card', 'Bank card', 'Default'],
    ['zh', '预付卡', '银行卡', '默认'],
  ] as const)('shows prepaid/null/default facts in %s', async (
    locale: AppLocale,
    prepaidLabel,
    bankCardLabel,
    defaultLabel,
  ) => {
    await AsyncStorage.setItem('@eslatin/locale', locale);
    const screen = render(
      <I18nProvider>
        <PaymentMethodsScreen />
      </I18nProvider>
    );

    await act(async () => {
      mockFocusEffect?.();
    });

    await waitFor(() => {
      expect(screen.getByText(`mercadopago · ${prepaidLabel}`)).toBeTruthy();
      expect(screen.getByText(`mercadopago · ${bankCardLabel}`)).toBeTruthy();
      expect(screen.getAllByText(defaultLabel).length).toBeGreaterThan(0);
    });
  });
});
