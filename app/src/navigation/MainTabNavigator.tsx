/**
 * 主应用底部导航
 */

import React from 'react';
import { StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
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

const Tab = createBottomTabNavigator<MainTabsParamList>();

export const MainTabNavigator = () => {
  const { t } = useI18n();

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: COLORS.IOS_BLUE,
        tabBarInactiveTintColor: COLORS.IOS_GRAY,
        tabBarStyle: {
          backgroundColor: COLORS.IOS_WHITE,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: COLORS.IOS_SEPARATOR,
          height: 60,
          paddingBottom: IOS_STYLES.SPACING.SM,
          paddingTop: IOS_STYLES.SPACING.SM,
        },
        tabBarLabelStyle: {
          fontSize: IOS_STYLES.FONT_SIZE.SMALL,
          fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
        },
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{
          tabBarLabel: t.tabs.home,
          tabBarIcon: ({ color, size }) => (
            <Icon name="home" library="Ionicons" size={size || 24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Saved"
        component={SavedScreen}
        options={{
          tabBarLabel: t.tabs.saved,
          tabBarIcon: ({ color, size }) => (
            <Icon name="heart" library="Ionicons" size={size || 24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Scan"
        component={ScanScreen}
        options={{
          tabBarLabel: t.tabs.scan,
          tabBarIcon: ({ color, size }) => (
            <Icon name="camera" library="Ionicons" size={size || 24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="MyWallet"
        component={MyWalletScreen}
        options={{
          tabBarLabel: t.tabs.wallet,
          tabBarIcon: ({ color, size }) => (
            <Icon name="wallet" library="Ionicons" size={size || 24} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Account"
        component={AccountScreen}
        options={{
          tabBarLabel: t.tabs.account,
          tabBarIcon: ({ color, size }) => (
            <Icon name="person" library="Ionicons" size={size || 24} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
};
