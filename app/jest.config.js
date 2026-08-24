module.exports = {
  preset: 'jest-expo',
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|react-redux|@reduxjs/toolkit|immer|expo-modules-core|expo-constants|expo-file-system|expo-asset|expo-font|@expo/vector-icons|react-native-safe-area-context|expo-location|@react-native-async-storage/async-storage|expo-status-bar|react-native-screens|react-native-vector-icons|react-native-gesture-handler|react-native-maps|@react-navigation/bottom-tabs|@react-navigation/stack|@react-navigation/elements|@react-navigation/core|expo|@react-navigation/native|uuid|axios|react-native-paper|@react-navigation|jest-expo|@testing-library/react-native|react-native-reanimated)',
  ],
  setupFilesAfterEnv: ['@testing-library/jest-native/extend-expect'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  moduleNameMapper: {
    '\\.(jpg|jpeg|png|gif|eot|otf|webp|svg|ttf|woff|woff2|mp4|webm|wav|mp3|m4a|aac|oga)$':
      '<rootDir>/assetsTransformer.js',
    '\\.(css|less)$': 'identity-obj-proxy',
  },
};
