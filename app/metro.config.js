const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// 在Web平台排除@rnmapbox/maps
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && moduleName.includes('@rnmapbox/maps')) {
    return { type: 'empty' };
  }
  // react-native-maps 仅原生；Web 走 GoogleMapView.web.tsx，此处兜底防止其它间接引用打进 Web 包
  if (platform === 'web' && (moduleName === 'react-native-maps' || moduleName.startsWith('react-native-maps/'))) {
    return { type: 'empty' };
  }

  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
