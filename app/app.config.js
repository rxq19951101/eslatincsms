/**
 * Expo 动态配置：从环境变量注入 Maps Key、Legal URL 等（EAS Build / 本地 .env）
 */
module.exports = ({ config }) => {
  const base = config;
  const googleMapsKey = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || '';
  const apiUrl = process.env.EXPO_PUBLIC_API_URL || '';
  const privacyUrl =
    process.env.EXPO_PUBLIC_PRIVACY_POLICY_URL ||
    (apiUrl ? `${apiUrl.replace(/\/$/, '')}/legal/privacy.html` : base.extra?.privacyPolicyUrl);
  const termsUrl =
    process.env.EXPO_PUBLIC_TERMS_URL ||
    (apiUrl ? `${apiUrl.replace(/\/$/, '')}/legal/terms.html` : base.extra?.termsOfServiceUrl);

  return {
    ...base,
    ios: {
      ...base.ios,
      ...(googleMapsKey
        ? {
            config: {
              ...(base.ios?.config || {}),
              googleMapsApiKey: googleMapsKey,
            },
          }
        : {}),
    },
    android: {
      ...base.android,
      ...(googleMapsKey
        ? {
            config: {
              ...(base.android?.config || {}),
              googleMaps: {
                apiKey: googleMapsKey,
              },
            },
          }
        : {}),
    },
    extra: {
      ...base.extra,
      privacyPolicyUrl: privacyUrl,
      termsOfServiceUrl: termsUrl,
      supportEmail: base.extra?.supportEmail || 'support@eslatin.com.co',
    },
  };
};
