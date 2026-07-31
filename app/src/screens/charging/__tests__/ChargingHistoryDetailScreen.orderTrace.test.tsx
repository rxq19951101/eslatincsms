import React from 'react';
import { render } from '@testing-library/react-native';

import ChargingHistoryDetailScreen from '../ChargingHistoryDetailScreen';
import { en as mockEn } from '../../../i18n/en';

const mockDispatch = jest.fn();
const mockSessionId = '11111111-1111-4111-8111-111111111111';
const internalChargePointId = '22222222-2222-4222-8222-222222222222';
const ocppIdentity = 'CO.BOGOTA:PRIVATE-CP-01';

let mockSelected: Record<string, unknown> | null;

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('@react-navigation/native', () => ({
  createNavigationContainerRef: () => ({
    isReady: () => false,
    navigate: jest.fn(),
    getCurrentRoute: jest.fn(),
  }),
  useNavigation: () => ({ goBack: jest.fn() }),
  useRoute: () => ({ params: { id: mockSessionId } }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      transactions: {
        selected: mockSelected,
        loadingDetail: false,
        error: null,
      },
    }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn, locale: 'en' }),
}));

jest.mock('../../../components/ui/ScreenHeader', () => {
  const { Text } = require('react-native');
  return ({ title }: { title: string }) => <Text>{title}</Text>;
});

describe('ChargingHistoryDetailScreen order trace', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSelected = {
      id: mockSessionId,
      transaction_id: 987654,
      charge_point_id: internalChargePointId,
      ocpp_identity: ocppIdentity,
      evse_id: '33333333-3333-4333-8333-333333333333',
      connector_id: 1,
      start_time: '2026-07-20T15:00:00Z',
      end_time: '2026-07-20T15:30:00Z',
      status: 'completed',
      energy_kwh: 12.34,
      duration_minutes: 30,
      meter_start: 1000,
      meter_stop: 13340,
      site_name: 'Bogotá Centro',
      site_address: 'Calle 100',
      invoice_number: 'INV-2026-001',
      total_amount: '437.40',
      currency: 'COP',
      billing_status: 'paid',
      connector_number: 1,
      connector_label: 'A01-1',
      charge_point_label: 'North entrance',
    };
  });

  it('renders authoritative invoice and public equipment labels without technical identifiers', () => {
    const screen = render(<ChargingHistoryDetailScreen />);

    expect(screen.getByText('INV-2026-001')).toBeTruthy();
    expect(screen.getByText('$437,40 COP')).toBeTruthy();
    expect(screen.getByText('Paid')).toBeTruthy();
    expect(screen.getByText('North entrance')).toBeTruthy();
    expect(screen.getByText('A01-1')).toBeTruthy();
    expect(screen.queryByText('987654')).toBeNull();
    expect(screen.queryByText(internalChargePointId)).toBeNull();
    expect(screen.queryByText(ocppIdentity)).toBeNull();
    expect(screen.queryByText('1000')).toBeNull();
    expect(screen.queryByText('13340')).toBeNull();
  });

  it('shows pending settlement without inventing an amount', () => {
    mockSelected = {
      ...mockSelected,
      invoice_number: null,
      total_amount: null,
      billing_status: null,
      connector_label: null,
      connector_number: 2,
    };

    const screen = render(<ChargingHistoryDetailScreen />);

    expect(screen.getAllByText(mockEn.history.pendingSettlement)).toHaveLength(2);
    expect(screen.getByText('Connector 2')).toBeTruthy();
    expect(screen.queryByText('INV-2026-001')).toBeNull();
    expect(screen.queryByText('$437,40 COP')).toBeNull();
  });
});
