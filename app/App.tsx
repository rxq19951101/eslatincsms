import React, { useEffect } from 'react';
import { Provider } from 'react-redux';
import { ActivityIndicator, StatusBar, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { store } from './src/store';
import { RootNavigator } from './src/navigation/RootNavigator';
import { useAppDispatch, useAppSelector } from './src/hooks/useRedux';
import { initializeAuth } from './src/store/slices/authSlice';
import { I18nProvider, useI18n } from './src/i18n';
import ActiveSessionRecovery from './src/components/charging/ActiveSessionRecovery';
import BrandLogo from './src/components/brand/BrandLogo';
import { palette, spacing } from './src/theme';

const AppContent = () => {
  const dispatch = useAppDispatch();
  const { isInitialized } = useAppSelector((state) => state.auth);
  const { t } = useI18n();

  useEffect(() => {
    // 初始化认证状态
    dispatch(initializeAuth());
  }, []);

  if (!isInitialized) {
    return (
      <View testID="app-initializing" style={styles.loadingContainer}>
        <StatusBar barStyle="dark-content" backgroundColor={palette.surface} />
        <BrandLogo style={styles.loadingLogo} />
        <ActivityIndicator
          color={palette.brand}
          accessibilityLabel={t.common.loading}
          accessibilityRole="progressbar"
        />
      </View>
    );
  }

  return (
    <>
      <StatusBar barStyle="dark-content" />
      <RootNavigator />
      <ActiveSessionRecovery />
    </>
  );
};

export default function App() {
  return (
    <SafeAreaProvider>
      <Provider store={store}>
        <I18nProvider>
          <AppContent />
        </I18nProvider>
      </Provider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: palette.surface,
    gap: spacing.md,
  },
  loadingLogo: {
    width: 224,
    height: 224,
  },
});
