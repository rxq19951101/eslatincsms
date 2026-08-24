/**
 * 主应用底部导航
 */

import React from 'react';
import { Platform, StyleSheet } from 'react-native';
import { BottomTabBar, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { MainTabsParamList } from '../types';
import { COLORS, IOS_STYLES } from '../constants/config';
import Icon from '../components/ui/Icon';
import { useI18n } from '../i18n';

// 导入页面组件
import HomeScreen from '../screens/home/HomeScreen';
import SavedScreen from '../screens/home/SavedScreen';
import ScanScreen from '../screens/charging/ScanScreen';
import MyWalletScreen from '../screens/wallet/MyWalletScreen';
import AccountScreen from '../screens/account/AccountScreen';
import ActiveChargingEntry from '../components/charging/ActiveChargingEntry';

const Tab = createBottomTabNavigator<MainTabsParamList>();

export const MainTabNavigator = () => {
  const { t } = useI18n();

  return (
    <Tab.Navigator
      tabBar={(props) => (
        <>
          <ActiveChargingEntry />
          <BottomTabBar {...props} />
        </>
      )}
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: COLORS.PRIMARY,
        tabBarInactiveTintColor: COLORS.TEXT_TERTIARY,
        tabBarStyle: {
          backgroundColor: COLORS.IOS_WHITE,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: COLORS.BORDER,
          height: Platform.OS === 'ios' ? 76 : 64,
          paddingBottom: Platform.OS === 'ios' ? 18 : 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: IOS_STYLES.FONT_WEIGHT.MEDIUM,
        },
        tabBarIconStyle: { marginBottom: -2 },
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{
          tabBarLabel: t.tabs.home,
          tabBarButtonTestID: 'app-tab-home',
          tabBarAccessibilityLabel: t.tabs.home,
          tabBarIcon: ({ color, size }) => (
            <Icon name="home-outline" library="Ionicons" size={size || 22} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Saved"
        component={SavedScreen}
        options={{
          tabBarLabel: t.tabs.saved,
          tabBarButtonTestID: 'app-tab-saved',
          tabBarAccessibilityLabel: t.tabs.saved,
          tabBarIcon: ({ color, size }) => (
            <Icon name="bookmark-outline" library="Ionicons" size={size || 22} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Scan"
        component={ScanScreen}
        options={{
          tabBarLabel: t.tabs.scan,
          tabBarButtonTestID: 'app-tab-scan',
          tabBarAccessibilityLabel: t.tabs.scan,
          tabBarIcon: ({ color, size }) => (
            <Icon name="scan-outline" library="Ionicons" size={size || 23} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="MyWallet"
        component={MyWalletScreen}
        options={{
          tabBarLabel: t.tabs.wallet,
          tabBarButtonTestID: 'app-tab-wallet',
          tabBarAccessibilityLabel: t.tabs.wallet,
          tabBarIcon: ({ color, size }) => (
            <Icon name="wallet-outline" library="Ionicons" size={size || 22} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Account"
        component={AccountScreen}
        options={{
          tabBarLabel: t.tabs.account,
          tabBarButtonTestID: 'app-tab-account',
          tabBarAccessibilityLabel: t.tabs.account,
          tabBarIcon: ({ color, size }) => (
            <Icon name="person-outline" library="Ionicons" size={size || 22} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
};
