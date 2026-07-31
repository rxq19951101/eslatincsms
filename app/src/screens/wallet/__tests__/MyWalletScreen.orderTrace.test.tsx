import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import MyWalletScreen from '../MyWalletScreen';
import { en as mockEn } from '../../../i18n/en';

const mockDispatch = jest.fn();
const mockNavigate = jest.fn();
const chargingSessionId = '11111111-1111-4111-8111-111111111111';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('@react-navigation/native', () => ({
  createNavigationContainerRef: () => ({
    isReady: () => false,
    navigate: jest.fn(),
    getCurrentRoute: jest.fn(),
  }),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      wallet: {
        balance: { balance: 50000, currency: 'COP' },
        transactions: [
          {
            id: 'charge-linked',
            type: 'charge',
            amount: -437.4,
            reference: 'WLT-CHARGE',
            created_at: '2026-07-20T15:30:00Z',
            charge_point_name: 'Bogotá Centro',
            charging_session_id: chargingSessionId,
          },
          {
            id: 'charge-unlinked',
            type: 'charge',
            amount: -100,
            reference: 'WLT-UNLINKED',
            created_at: '2026-07-19T15:30:00Z',
            charging_session_id: null,
          },
          {
            id: 'top-up',
            type: 'top_up',
            amount: 20000,
            reference: 'WLT-TOPUP',
            created_at: '2026-07-18T15:30:00Z',
            charging_session_id: chargingSessionId,
          },
        ],
        loadingBalance: false,
        loadingTx: false,
        toppingUp: false,
        error: null,
      },
    }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn, locale: 'en' }),
}));

jest.mock('../../../components/ui/RootTabHeader', () => {
  const { Text } = require('react-native');
  return ({ title }: { title: string }) => <Text>{title}</Text>;
});

describe('MyWalletScreen order trace', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('opens order detail only for a linked charge transaction', () => {
    const screen = render(<MyWalletScreen />);
    const rows = screen.getAllByTestId('app-wallet-transaction');

    fireEvent.press(rows[0]);
    fireEvent.press(rows[1]);
    fireEvent.press(rows[2]);

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('ChargingHistoryDetail', {
      id: chargingSessionId,
    });
  });
});
