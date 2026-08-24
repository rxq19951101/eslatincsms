import { ActionSheetIOS, Alert, Linking } from 'react-native';

import {
  buildAppleMapsDirectionsUrl,
  buildGoogleMapsDirectionsUrl,
  buildWazeDirectionsUrl,
  getNavigationProviders,
  hasValidNavigationCoordinates,
  openNavigationProvider,
  showExternalNavigationOptions,
} from '../externalNavigation';

const copy = {
  title: 'Choose navigation',
  message: 'Choose an app',
  googleMaps: 'Google Maps',
  waze: 'Waze',
  appleMaps: 'Apple Maps',
  cancel: 'Cancel',
  openFailedTitle: 'Cannot navigate',
  openFailedMessage: 'Cannot open map',
};

describe('externalNavigation', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('builds official universal direction URLs without a fake place id', () => {
    expect(buildGoogleMapsDirectionsUrl(4.6872, -74.0565)).toBe(
      'https://www.google.com/maps/dir/?api=1&destination=4.6872%2C-74.0565&travelmode=driving',
    );
    expect(buildWazeDirectionsUrl(4.6872, -74.0565)).toBe(
      'https://waze.com/ul?ll=4.6872%2C-74.0565&navigate=yes&utm_source=eslatin',
    );
    expect(buildAppleMapsDirectionsUrl(4.6872, -74.0565, 'Estación Norte')).toBe(
      'https://maps.apple.com/?daddr=4.6872%2C-74.0565&q=Estaci%C3%B3n%20Norte&dirflg=d',
    );
  });

  it('accepts zero coordinates and rejects invalid or out-of-range values', () => {
    expect(hasValidNavigationCoordinates(0, 0)).toBe(true);
    expect(hasValidNavigationCoordinates('4.6872', '-74.0565')).toBe(true);
    expect(hasValidNavigationCoordinates(undefined, -74)).toBe(false);
    expect(hasValidNavigationCoordinates(91, -74)).toBe(false);
    expect(hasValidNavigationCoordinates(4, -181)).toBe(false);
  });

  it('offers Apple Maps only on iOS', () => {
    expect(getNavigationProviders('ios')).toEqual(['googleMaps', 'waze', 'appleMaps']);
    expect(getNavigationProviders('android')).toEqual(['googleMaps', 'waze']);
  });

  it('shows Google Maps and Waze on Android and opens the chosen provider', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    const openUrlSpy = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);

    showExternalNavigationOptions({
      latitude: 4.6872,
      longitude: -74.0565,
      label: 'Estación Norte',
      copy,
      platform: 'android',
    });

    const buttons = alertSpy.mock.calls[0][2];
    expect(buttons?.map((button) => button.text)).toEqual(['Google Maps', 'Waze', 'Cancel']);

    buttons?.[1].onPress?.();
    await Promise.resolve();

    expect(openUrlSpy).toHaveBeenCalledWith(
      'https://waze.com/ul?ll=4.6872%2C-74.0565&navigate=yes&utm_source=eslatin',
    );
  });

  it('shows all three navigation providers on iOS', async () => {
    const sheetSpy = jest
      .spyOn(ActionSheetIOS, 'showActionSheetWithOptions')
      .mockImplementation((_options, callback) => callback(2));
    const openUrlSpy = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);

    showExternalNavigationOptions({
      latitude: 4.6872,
      longitude: -74.0565,
      label: 'Estación Norte',
      copy,
      platform: 'ios',
    });
    await Promise.resolve();

    expect(sheetSpy.mock.calls[0][0].options).toEqual([
      'Google Maps',
      'Waze',
      'Apple Maps',
      'Cancel',
    ]);
    expect(openUrlSpy).toHaveBeenCalledWith(
      'https://maps.apple.com/?daddr=4.6872%2C-74.0565&q=Estaci%C3%B3n%20Norte&dirflg=d',
    );
  });

  it('uses Google Maps directly on web and reports open failures', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    jest.spyOn(Linking, 'openURL').mockRejectedValue(new Error('cannot open'));

    showExternalNavigationOptions({
      latitude: 4.6872,
      longitude: -74.0565,
      label: 'Estación Norte',
      copy,
      platform: 'web',
    });
    await Promise.resolve();
    await Promise.resolve();

    expect(alertSpy).toHaveBeenCalledWith('Cannot navigate', 'Cannot open map');

    alertSpy.mockClear();
    await openNavigationProvider('waze', {
      latitude: 4.6872,
      longitude: -74.0565,
      label: 'Estación Norte',
      copy,
    });
    expect(alertSpy).toHaveBeenCalledWith('Cannot navigate', 'Cannot open map');
  });
});
