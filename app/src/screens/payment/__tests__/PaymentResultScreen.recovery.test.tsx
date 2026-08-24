import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import PaymentResultScreen from '../PaymentResultScreen';
import { en as mockEn } from '../../../i18n/en';
import { resolveCheckoutSession } from '../../../features/payment/checkoutCoordinator';

const mockNavigation = {
  goBack: jest.fn(),
  navigate: jest.fn(),
};
const mockDispatch = jest.fn();
let mockRouteParams: {
  checkout_session_id?: string;
  status?: 'approved' | 'processing';
} = { checkout_session_id: 'checkout-1', status: 'approved' };

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => mockNavigation,
  useRoute: () => ({ params: mockRouteParams }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
}));

jest.mock('../../../store/slices/walletSlice', () => ({
  fetchWalletBalance: jest.fn(() => ({ type: 'wallet/fetch' })),
}));

jest.mock('../../../api/payments', () => ({
  getPaymentOrderStatus: jest.fn(),
  isAllowedMercadoPagoActionUrl: jest.fn(() => false),
}));

jest.mock('../../../features/payment/checkoutCoordinator', () => ({
  clearPendingCheckoutSession: jest.fn(),
  isCheckoutTerminal: (status: string) =>
    status === 'approved' || status === 'declined' || status === 'expired' || status === 'error',
  resolveCheckoutSession: jest.fn(),
}));

jest.mock('../../../components/ui/Screen', () => {
  const { View } = require('react-native');
  return ({ children }: { children: React.ReactNode }) => <View>{children}</View>;
});

jest.mock('../../../components/ui/ScreenHeader', () => {
  const { View } = require('react-native');
  return () => <View />;
});

jest.mock('../../../components/ui/Badge', () => {
  const { Text } = require('react-native');
  return ({ label }: { label: string }) => <Text>{label}</Text>;
});

jest.mock('../../../components/ui/Button', () => {
  const { Text, TouchableOpacity } = require('react-native');
  return ({ title, onPress, disabled, testID }: {
    title: string;
    onPress: () => void;
    disabled?: boolean;
    testID?: string;
  }) => (
    <TouchableOpacity testID={testID} disabled={disabled} onPress={onPress}>
      <Text>{title}</Text>
    </TouchableOpacity>
  );
});

const mockedResolve = resolveCheckoutSession as jest.MockedFunction<typeof resolveCheckoutSession>;

describe('PaymentResultScreen checkout recovery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRouteParams = { checkout_session_id: 'checkout-1', status: 'approved' };
  });

  it('ignores a deep-link success hint when the network cannot confirm server state', async () => {
    mockedResolve.mockResolvedValue({
      kind: 'network_unknown',
      session: null,
      purpose: 'charging_direct',
      source: 'charging_direct',
    });

    const screen = render(<PaymentResultScreen />);

    expect(await screen.findByTestId('app-checkout-recovery-network_unknown')).toBeTruthy();
    expect(screen.queryByText(mockEn.payment.resultOkTitle)).toBeNull();
    expect(screen.getByTestId('app-checkout-refresh')).toBeTruthy();
  });

  it('retries only the original submitted session', async () => {
    mockedResolve.mockResolvedValue({
      kind: 'already_submitted',
      session: null,
      purpose: 'charging_direct',
      source: 'charging_direct',
    });

    const screen = render(<PaymentResultScreen />);
    const refresh = await screen.findByTestId('app-checkout-refresh');
    fireEvent.press(refresh);

    await waitFor(() => expect(mockedResolve).toHaveBeenCalledTimes(2));
    expect(mockedResolve).toHaveBeenNthCalledWith(1, 'checkout-1');
    expect(mockedResolve).toHaveBeenNthCalledWith(2, 'checkout-1');
  });

  it('clears the expired flow through an explicit source-aware restart action', async () => {
    mockedResolve.mockResolvedValue({
      kind: 'expired_or_missing',
      session: null,
      purpose: 'save_card',
      source: 'add_payment',
    });

    const screen = render(<PaymentResultScreen />);
    fireEvent.press(await screen.findByTestId('app-checkout-restart'));

    expect(mockNavigation.navigate).toHaveBeenCalledWith('AddPayment');
  });
});
