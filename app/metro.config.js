const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// 在Web平台排除@rnmapbox/maps
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && moduleName.includes('@rnmapbox/maps')) {
    // 返回一个空模块用于Web平台
    return {
      type: 'empty',
    };
  }
  
  // 其他情况使用默认解析
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
