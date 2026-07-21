import React from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import ChargingProcessScreen from '../ChargingProcessScreen';
import chargingReducer from '../../../store/slices/chargingSlice';
import walletReducer, { setBalance } from '../../../store/slices/walletSlice';
import {
  checkChargerStatus,
  getActiveChargingSession,
  getMeterValues,
  startChargingByScan,
  stopCharging,
  type ActiveChargingSession,
} from '../../../api/charging';

const mockNavigation = {
  goBack: jest.fn(),
  navigate: jest.fn(),
  replace: jest.fn(),
};
let mockRouteParams: { qrToken?: string; sessionId?: string } = { qrToken: 'public-qr-token' };

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => mockNavigation,
  useRoute: () => ({ params: mockRouteParams }),
  useIsFocused: () => true,
  createNavigationContainerRef: () => ({ isReady: () => false, reset: jest.fn() }),
}));

jest.mock('../../../api/charging', () => ({
  checkChargerStatus: jest.fn(),
  getActiveChargingSession: jest.fn(),
  getMeterValues: jest.fn(),
  startChargingByScan: jest.fn(),
  stopCharging: jest.fn(),
}));

jest.mock('../../../api/wallet', () => ({
  getWalletBalance: jest.fn(() => Promise.resolve({ balance: 100000, currency: 'COP' })),
  getWalletTransactions: jest.fn(() => Promise.resolve([])),
  topUpWallet: jest.fn(),
}));

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return (props: Record<string, unknown>) => <View {...props} />;
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

jest.mock('../../../components/ui/CircularProgress', () => {
  const { View } = require('react-native');
  return () => <View />;
});

jest.mock('../../../components/ui/Skeleton', () => {
  const { View } = require('react-native');
  return () => <View />;
});

const mockedCheck = checkChargerStatus as jest.MockedFunction<typeof checkChargerStatus>;
const mockedStartApi = startChargingByScan as jest.MockedFunction<typeof startChargingByScan>;
const mockedActiveApi = getActiveChargingSession as jest.MockedFunction<typeof getActiveChargingSession>;
const mockedMeterApi = getMeterValues as jest.MockedFunction<typeof getMeterValues>;
const mockedStopApi = stopCharging as jest.MockedFunction<typeof stopCharging>;

const activeSession: ActiveChargingSession = {
  id: '11111111-1111-4111-8111-111111111111',
  transaction_id: 731,
  charge_point_id: '22222222-2222-4222-8222-222222222222',
  ocpp_identity: 'CP-PUBLIC-001',
  connector_id: 1,
  evse_id: '33333333-3333-4333-8333-333333333333',
  id_tag: 'APP-user',
  start_time: '2026-07-18T12:00:00Z',
  end_time: null,
  status: 'ongoing',
  meter_start: 1000,
  meter_stop: null,
};

describe('ChargingProcessScreen start button', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRouteParams = { qrToken: 'public-qr-token' };
    mockedCheck.mockResolvedValue({
      charger_id: 'internal-charge-point-id',
      ocpp_identity: 'CP-PUBLIC-001',
      connector_id: 1,
      status: 'available',
      is_online: true,
      connector_status: 'Available',
      charger_info: { site_name: 'QA Station', price_per_kwh: 1200 },
    });
  });

  it('sends at most one start for a rapid repeated press', async () => {
    mockedStartApi.mockImplementation(() => new Promise(() => {}));
    const store = configureStore({
      reducer: { charging: chargingReducer, wallet: walletReducer },
    });
    store.dispatch(setBalance({ balance: 100000, currency: 'COP' }));
    const screen = render(
      <Provider store={store}>
        <ChargingProcessScreen />
      </Provider>
    );
    const startButton = await waitFor(() => screen.getByTestId('app-charging-start'));

    fireEvent.press(startButton);
    fireEvent.press(startButton);

    expect(mockedStartApi).toHaveBeenCalledTimes(1);
    expect(mockedStartApi).toHaveBeenCalledWith({ qrToken: 'public-qr-token' });
    screen.unmount();
  });

  it('polls and stops a recovered session without a QR token and never starts', async () => {
    mockRouteParams = { sessionId: activeSession.id };
    mockedActiveApi.mockResolvedValue(activeSession);
    mockedMeterApi.mockResolvedValue([]);
    mockedStopApi.mockResolvedValue({ success: true });
    const initialCharging = chargingReducer(undefined, { type: 'test/init' });
    const initialWallet = walletReducer(undefined, { type: 'test/init' });
    const store = configureStore({
      reducer: { charging: chargingReducer, wallet: walletReducer },
      preloadedState: {
        charging: { ...initialCharging, activeSession, recoveryChecked: true },
        wallet: { ...initialWallet, balance: { balance: 100000, currency: 'COP' } },
      },
    });
    const screen = render(
      <Provider store={store}>
        <ChargingProcessScreen />
      </Provider>
    );

    const stopButton = await waitFor(() => screen.getByTestId('app-charging-stop'));
    await waitFor(() => expect(mockedActiveApi).toHaveBeenCalledWith(undefined));
    expect(mockedCheck).not.toHaveBeenCalled();
    expect(mockedStartApi).not.toHaveBeenCalled();

    fireEvent.press(stopButton);
    await waitFor(() => expect(mockedStopApi).toHaveBeenCalledWith(activeSession.id));
    expect(mockedStartApi).not.toHaveBeenCalled();
    screen.unmount();
  });
});
