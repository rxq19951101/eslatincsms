//
// 本文件为 Expo Babel 配置，占位即可满足基础需求。
// 支持 React Native 与 TS。

module.exports = function(api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'],
  };
};


