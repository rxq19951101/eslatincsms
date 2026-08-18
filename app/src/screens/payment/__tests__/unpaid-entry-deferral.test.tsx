import React from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import PaymentHubScreen from '../PaymentHubScreen';
import ChargingCompleteScreen from '../../charging/ChargingCompleteScreen';
import walletReducer from '../../../store/slices/walletSlice';
import chargingReducer from '../../../store/slices/chargingSlice';
import { settleCharging } from '../../../api/charging';
import type { ActiveChargingSession, SettleResult } from '../../../api/charging';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

const mockNavigation = {
  goBack: jest.fn(),
  navigate: jest.fn(),
};
let mockRouteParams: { ocppIdentity?: string } = {};

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => mockNavigation,
  useRoute: () => ({ params: mockRouteParams }),
  useFocusEffect: () => undefined,
  createNavigationContainerRef: () => ({ isReady: () => false }),
}));

jest.mock('../../../api/wallet', () => ({
  getWalletBalance: jest.fn(() => Promise.resolve({ balance: 100000, currency: 'COP' })),
  getWalletTransactions: jest.fn(() => Promise.resolve([])),
  topUpWallet: jest.fn(),
}));

jest.mock('../../../api/charging', () => ({
  settleCharging: jest.fn(),
}));

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return (props: Record<string, unknown>) => <View {...props} />;
});

const mockedSettle = settleCharging as jest.MockedFunction<typeof settleCharging>;

const stoppedSession: ActiveChargingSession = {
  id: '11111111-1111-4111-8111-111111111111',
  transaction_id: 731,
  charge_point_id: '22222222-2222-4222-8222-222222222222',
  ocpp_identity: 'CP-PUBLIC-001',
  connector_id: 1,
  evse_id: '33333333-3333-4333-8333-333333333333',
  id_tag: 'APP-user',
  start_time: '2026-07-18T12:00:00Z',
  end_time: '2026-07-18T12:30:00Z',
  status: 'completed',
  meter_start: 1000,
  meter_stop: 2000,
};

const unpaidSettlement: SettleResult = {
  invoice_id: '33333333-3333-4333-8333-333333333333',
  settlement_method: 'direct_card',
  payment_status: 'unpaid',
  payment_order_id: '44444444-4444-4444-8444-444444444444',
  charged_amount: '18760.00',
  currency: 'COP',
  energy_kwh: '6.80',
  price_per_kwh: '2760.00',
  balance: null,
  next_action: null,
  already_settled: false,
};

describe('deferred unpaid-bill entry points', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRouteParams = {};
  });

  it('does not render an unpaid-bills entry from PaymentHub', () => {
    const store = configureStore({ reducer: { wallet: walletReducer } });
    const screen = render(
      <Provider store={store}>
        <PaymentHubScreen />
      </Provider>
    );

    expect(screen.queryByText('Facturas pendientes')).toBeNull();
    expect(mockNavigation.navigate).not.toHaveBeenCalledWith('UnpaidBills');
    screen.unmount();
  });

  it('shows a deferred message and an unpaid-bills action after unpaid settlement', async () => {
    mockedSettle.mockResolvedValue(unpaidSettlement);
    const initialCharging = chargingReducer(undefined, { type: 'test/init' });
    const initialWallet = walletReducer(undefined, { type: 'test/init' });
    const store = configureStore({
      reducer: { charging: chargingReducer, wallet: walletReducer },
      preloadedState: {
        charging: { ...initialCharging, lastStoppedSession: stoppedSession },
        wallet: initialWallet,
      },
    });

    const screen = render(
      <Provider store={store}>
        <ChargingCompleteScreen />
      </Provider>
    );

    await waitFor(() => expect(screen.getByTestId('app-charging-unpaid-deferred')).toBeTruthy());
    expect(screen.getByTestId('app-charging-unpaid-action')).toBeTruthy();
    fireEvent.press(screen.getByTestId('app-charging-unpaid-action'));
    expect(mockNavigation.navigate).toHaveBeenCalledWith('UnpaidBills');
    screen.unmount();
  });
});
