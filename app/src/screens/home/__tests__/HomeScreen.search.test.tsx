import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import HomeScreen from '../HomeScreen';
import { en } from '../../../i18n/en';
import { es } from '../../../i18n/es';
import { zh } from '../../../i18n/zh';

const mockDispatch = jest.fn();
let mockTranslations: typeof en | typeof es | typeof zh = en;

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

const mockSites = [
  {
    id: 'site-name',
    name: 'Alpha Plaza',
    address: 'Avenida Norte 10',
    latitude: 4.61,
    longitude: -74.08,
    status: 'Available',
    charger_count: 1,
    available_connectors: 1,
    total_connectors: 1,
    connector_types: ['Type2'],
    charging_options: [],
    has_pricing: false,
    is_favorite: false,
  },
  {
    id: 'site-address',
    name: 'Beta Point',
    address: 'Calle Luna 20',
    latitude: 4.62,
    longitude: -74.09,
    status: 'Available',
    charger_count: 1,
    available_connectors: 1,
    total_connectors: 1,
    connector_types: ['CHAdeMO'],
    charging_options: [],
    has_pricing: false,
    is_favorite: false,
  },
  {
    id: 'site-connector',
    name: 'Gamma Hub',
    address: 'Carrera Sur 30',
    latitude: 4.63,
    longitude: -74.1,
    status: 'Available',
    charger_count: 1,
    available_connectors: 1,
    total_connectors: 1,
    connector_types: ['CCS2'],
    charging_options: [],
    has_pricing: false,
    is_favorite: false,
  },
];

jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: jest.fn(() => Promise.resolve({ status: 'denied' })),
  getCurrentPositionAsync: jest.fn(),
}));

jest.mock('@react-navigation/native', () => ({
  createNavigationContainerRef: () => ({
    isReady: () => false,
    navigate: jest.fn(),
    getCurrentRoute: jest.fn(),
  }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) => selector({
    site: {
      sites: mockSites,
      selectedSite: null,
      loading: false,
      error: null,
    },
  }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockTranslations }),
}));

jest.mock('../../../components/GoogleMapView', () => {
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: () => <View />,
  };
});

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: () => <View />,
  };
});

jest.mock('../../../components/ui/RootTabHeader', () => {
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: () => <View />,
  };
});

describe('HomeScreen search', () => {
  beforeEach(() => {
    mockTranslations = en;
    mockDispatch.mockClear();
  });

  it.each([
    ['English', en, en.home.search],
    ['Spanish', es, es.home.search],
    ['Chinese', zh, zh.home.search],
  ])('renders the complete %s placeholder', (_language, translations, placeholder) => {
    mockTranslations = translations;

    const screen = render(<HomeScreen />);

    expect(screen.getByPlaceholderText(placeholder)).toBeTruthy();
  });

  it('uses stable full-width layout and native search input behavior', () => {
    const screen = render(<HomeScreen />);
    const searchContainer = screen.getByTestId('home-search-container');
    const searchInput = screen.getByTestId('home-search-input');
    const fieldWrapper = searchInput.parent;
    const containerStyle = StyleSheet.flatten(searchContainer.props.style);
    const wrapperStyle = StyleSheet.flatten(fieldWrapper?.props.style);
    const inputStyle = StyleSheet.flatten(searchInput.props.style);

    expect(containerStyle).toMatchObject({ width: '100%' });
    expect(containerStyle.position).not.toBe('absolute');
    expect(containerStyle.marginTop ?? 0).toBeGreaterThanOrEqual(0);
    expect(wrapperStyle).toMatchObject({ width: '100%' });
    expect(wrapperStyle.flex).toBeUndefined();
    expect(inputStyle).toMatchObject({ width: '100%', minHeight: 52 });
    expect(inputStyle.flex).toBeUndefined();
    expect(searchInput.props).toMatchObject({
      autoComplete: 'off',
      autoCorrect: false,
      clearButtonMode: 'while-editing',
      importantForAutofill: 'no',
      returnKeyType: 'search',
      textContentType: 'none',
    });
  });

  it.each([
    ['station name', 'alpha', 'Alpha Plaza'],
    ['address', 'luna', 'Beta Point'],
    ['connector type', 'ccs2', 'Gamma Hub'],
  ])('filters by %s and restores all sites when cleared', (_field, query, match) => {
    const screen = render(<HomeScreen />);
    const searchInput = screen.getByTestId('home-search-input');

    fireEvent.changeText(searchInput, query);

    expect(screen.getByText(match)).toBeTruthy();
    expect(screen.queryByText('List (1)')).toBeTruthy();

    fireEvent.changeText(searchInput, '');

    expect(screen.getByText('List (3)')).toBeTruthy();
    mockSites.forEach((site) => {
      expect(screen.getByText(site.name)).toBeTruthy();
    });
  });
});
