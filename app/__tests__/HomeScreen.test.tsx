import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import HomeScreen from '../src/screens/home/HomeScreen';
import chargerReducer from '../src/store/slices/chargerSlice';
import authReducer from '../src/store/slices/authSlice';
import { NavigationContainer } from '@react-navigation/native';
import type { ReactNode } from 'react';

// Mock AsyncStorage
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

// Mock依赖
jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: jest.fn(() => Promise.resolve({ status: 'granted' })),
  getCurrentPositionAsync: jest.fn(() => Promise.resolve({
    coords: { latitude: 37.78825, longitude: -122.4324 }
  })),
}));

// Mock react-native-maps
jest.mock('react-native-maps', () => {
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: (props: Record<string, unknown>) => <View testID="google-map-view" {...props} />,
    Marker: (props: Record<string, unknown>) => <View testID="map-marker" {...props} />,
    PROVIDER_GOOGLE: 'google',
  };
});

// Mock GoogleMapView组件
jest.mock('../src/components/GoogleMapView', () => {
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: (props: { children?: ReactNode }) => <View testID="google-map-view-component">{props.children}</View>,
  };
});

// Mock API client
jest.mock('../src/api/client', () => {
  return {
    __esModule: true,
    default: {
      get: jest.fn(() => Promise.resolve({ data: [] })),
      post: jest.fn(() => Promise.resolve({ data: {} })),
    },
  };
});

// Mock chargers API
jest.mock('../src/api/chargers', () => ({
  getChargers: jest.fn(() => Promise.resolve([])),
  getNearbyChargers: jest.fn(() => Promise.resolve([])),
}));

describe('HomeScreen Integration Test', () => {
  const mockStore = configureStore({
    reducer: {
      charger: chargerReducer,
      auth: authReducer,
    },
    preloadedState: {
      charger: {
        chargers: [
          {
            id: 'CP001',
            site_name: 'Test Station',
            latitude: 37.78825,
            longitude: -122.4324,
            status: 'Available',
            available_connectors: 2,
            total_connectors: 4,
            is_configured: true,
            has_location: true,
            has_pricing: false,
          }
        ],
        loading: false,
        error: null,
        selectedCharger: null,
        lastFetch: null,
        filters: {},
      },
    },
  });

  const renderWithProviders = (component: ReactNode) => {
    return render(
      <Provider store={mockStore}>
        <NavigationContainer>
          {component}
        </NavigationContainer>
      </Provider>
    );
  };

  it('renders correctly and toggles between list and map view', async () => {
    const { getByText, getByTestId } = renderWithProviders(<HomeScreen />);

    // 初始状态应该显示列表
    expect(getByText('Test Station')).toBeTruthy();
    
    // 切换到地图视图
    // 默认 locale 是西语；同时兼容测试环境中持久化为中文的情况。
    const mapButton = getByText(/^(Mapa|地图)$/);
    fireEvent.press(mapButton);

    // 验证地图组件是否渲染 (使用了我们修复后的 GoogleMapView)
    // 注意：由于我们mock了组件，这里主要验证渲染路径没有崩溃，并且正确的组件被调用
    await waitFor(() => {
      // 检查是否试图渲染地图组件
      // 如果之前报错 ReferenceError: CustomMapView doesn't exist，这里就会失败
      expect(getByTestId('google-map-view-component')).toBeTruthy();
    });
  });
});
