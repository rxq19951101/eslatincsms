import React, { useEffect } from 'react';
import { Provider } from 'react-redux';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { store } from './src/store';
import { RootNavigator } from './src/navigation/RootNavigator';
import { useAppDispatch, useAppSelector } from './src/hooks/useRedux';
import { initializeAuth } from './src/store/slices/authSlice';
import { I18nProvider } from './src/i18n';

const AppContent = () => {
  const dispatch = useAppDispatch();
  const { isInitialized } = useAppSelector((state) => state.auth);

  useEffect(() => {
    // 初始化认证状态
    dispatch(initializeAuth());
  }, []);

  if (!isInitialized) {
    // TODO: 显示启动画面
    return null;
  }

  return (
    <>
      <StatusBar barStyle="dark-content" />
      <RootNavigator />
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
