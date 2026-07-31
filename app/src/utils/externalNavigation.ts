import { ActionSheetIOS, Alert, Linking, Platform } from 'react-native';

export type NavigationProvider = 'googleMaps' | 'waze' | 'appleMaps';

export type ExternalNavigationCopy = {
  title: string;
  message: string;
  googleMaps: string;
  waze: string;
  appleMaps: string;
  cancel: string;
  openFailedTitle: string;
  openFailedMessage: string;
};

type ExternalNavigationParams = {
  latitude: number;
  longitude: number;
  label: string;
  copy: ExternalNavigationCopy;
  platform?: typeof Platform.OS;
};

export const hasValidNavigationCoordinates = (
  latitude: unknown,
  longitude: unknown,
): boolean => {
  const lat = Number(latitude);
  const lng = Number(longitude);

  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
};

export const buildGoogleMapsDirectionsUrl = (latitude: number, longitude: number): string =>
  `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
    `${latitude},${longitude}`,
  )}&travelmode=driving`;

export const buildWazeDirectionsUrl = (latitude: number, longitude: number): string =>
  `https://waze.com/ul?ll=${encodeURIComponent(
    `${latitude},${longitude}`,
  )}&navigate=yes&utm_source=eslatin`;

export const buildAppleMapsDirectionsUrl = (
  latitude: number,
  longitude: number,
  label: string,
): string =>
  `https://maps.apple.com/?daddr=${encodeURIComponent(
    `${latitude},${longitude}`,
  )}&q=${encodeURIComponent(label)}&dirflg=d`;

export const getNavigationProviders = (
  platform: typeof Platform.OS,
): NavigationProvider[] =>
  platform === 'ios'
    ? ['googleMaps', 'waze', 'appleMaps']
    : ['googleMaps', 'waze'];

const getNavigationUrl = (
  provider: NavigationProvider,
  latitude: number,
  longitude: number,
  label: string,
): string => {
  if (provider === 'waze') {
    return buildWazeDirectionsUrl(latitude, longitude);
  }
  if (provider === 'appleMaps') {
    return buildAppleMapsDirectionsUrl(latitude, longitude, label);
  }
  return buildGoogleMapsDirectionsUrl(latitude, longitude);
};

export const openNavigationProvider = async (
  provider: NavigationProvider,
  params: Pick<ExternalNavigationParams, 'latitude' | 'longitude' | 'label' | 'copy'>,
): Promise<void> => {
  try {
    await Linking.openURL(
      getNavigationUrl(provider, params.latitude, params.longitude, params.label),
    );
  } catch {
    Alert.alert(params.copy.openFailedTitle, params.copy.openFailedMessage);
  }
};

export const showExternalNavigationOptions = ({
  latitude,
  longitude,
  label,
  copy,
  platform = Platform.OS,
}: ExternalNavigationParams): void => {
  if (platform === 'web') {
    void openNavigationProvider('googleMaps', { latitude, longitude, label, copy });
    return;
  }

  const providers = getNavigationProviders(platform);
  const providerLabels: Record<NavigationProvider, string> = {
    googleMaps: copy.googleMaps,
    waze: copy.waze,
    appleMaps: copy.appleMaps,
  };
  const openProvider = (provider: NavigationProvider) => {
    void openNavigationProvider(provider, { latitude, longitude, label, copy });
  };

  if (platform === 'ios') {
    const options = [...providers.map((provider) => providerLabels[provider]), copy.cancel];
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: copy.title,
        message: copy.message,
        options,
        cancelButtonIndex: options.length - 1,
      },
      (selectedIndex) => {
        const provider = providers[selectedIndex];
        if (provider) openProvider(provider);
      },
    );
    return;
  }

  Alert.alert(
    copy.title,
    copy.message,
    [
      ...providers.map((provider) => ({
        text: providerLabels[provider],
        onPress: () => openProvider(provider),
      })),
      { text: copy.cancel, style: 'cancel' as const },
    ],
  );
};
