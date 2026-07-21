import React from 'react';
import { render } from '@testing-library/react-native';

import StationDetailScreen from '../StationDetailScreen';
import { en } from '../../../i18n/en';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

const mockDispatch = jest.fn(() => ({ unwrap: () => Promise.resolve() }));
const mockTranslations = en;
const mockSiteId = '11111111-1111-4111-8111-111111111111';
const internalChargerId = '22222222-2222-4222-8222-222222222222';
const internalConnectorId = '33333333-3333-4333-8333-333333333333';
const ocppIdentity = 'CO.BOGOTA:PRIVATE-CP-01';

const mockSite = {
  id: mockSiteId,
  name: 'Bogotá Centro',
  address: 'Calle 100 # 10-20',
  latitude: 4.61,
  longitude: -74.08,
  status: 'Available',
  charger_count: 1,
  available_connectors: 1,
  total_connectors: 1,
  connector_types: ['Type2'],
  charging_options: [],
  max_power_kw: 7,
  price_per_kwh: 2700,
  has_pricing: true,
  is_favorite: false,
  charge_points: [{
    id: internalChargerId,
    ocpp_identity: ocppIdentity,
    display_code: 'A01',
    display_name: 'North entrance',
    location_hint: 'P2 / bay 42',
    status: 'Available',
    vendor: 'EsLatin',
    model: 'AC7',
    connectors: [{
      id: internalConnectorId,
      connector_id: 1,
      physical_reference: 'A01-1',
      status: 'Charging',
      connector_type: 'Type2',
      power_kw: 7,
    }],
  }],
};

jest.mock('@react-navigation/native', () => ({
  createNavigationContainerRef: () => ({ isReady: () => false, reset: jest.fn() }),
  useNavigation: () => ({ goBack: jest.fn(), navigate: jest.fn() }),
  useRoute: () => ({ params: { siteId: mockSiteId } }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) => selector({
    site: { selectedSite: mockSite, loading: false, error: null },
  }),
}));

jest.mock('../../../i18n', () => ({ useI18n: () => ({ t: mockTranslations }) }));
jest.mock('../../../components/GoogleMapView', () => {
  const { View } = require('react-native');
  return () => <View />;
});
jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return () => <View />;
});

describe('StationDetailScreen public charger labels', () => {
  it('renders public charger and connector cards without technical identities', () => {
    const screen = render(<StationDetailScreen />);

    expect(screen.getByText('North entrance')).toBeTruthy();
    expect(screen.getByText('A01')).toBeTruthy();
    expect(screen.getByText('P2 / bay 42')).toBeTruthy();
    expect(screen.getByText('A01-1')).toBeTruthy();
    expect(screen.getByText('Type 2 · 7 kW')).toBeTruthy();
    expect(screen.getByText('Charging')).toBeTruthy();
    expect(screen.queryByText(internalChargerId)).toBeNull();
    expect(screen.queryByText(internalConnectorId)).toBeNull();
    expect(screen.queryByText(ocppIdentity)).toBeNull();
  });
});
