/**
 * 主导航配置
 */

import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import type { RootStackParamList } from '../types';

// Auth Screens
import WelcomeScreen from '../screens/auth/WelcomeScreen';
import EmailLoginScreen from '../screens/auth/EmailLoginScreen';
import EmailRegisterScreen from '../screens/auth/EmailRegisterScreen';
import EmailVerificationScreen from '../screens/auth/EmailVerificationScreen';
import VerificationSuccessScreen from '../screens/auth/VerificationSuccessScreen';
import ForgotPasswordScreen from '../screens/auth/ForgotPasswordScreen';
import ResetPasswordScreen from '../screens/auth/ResetPasswordScreen';

// Main App Screens
import LocationPermissionScreen from '../screens/home/LocationPermissionScreen';
import StationDetailScreen from '../screens/home/StationDetailScreen';
import ChargingProcessScreen from '../screens/charging/ChargingProcessScreen';
import ChargingCompleteScreen from '../screens/charging/ChargingCompleteScreen';
import ChargingHistoryScreen from '../screens/charging/ChargingHistoryScreen';
import ChargingHistoryDetailScreen from '../screens/charging/ChargingHistoryDetailScreen';
import PersonalInfoScreen from '../screens/account/PersonalInfoScreen';
import PaymentMethodsScreen from '../screens/account/PaymentMethodsScreen';
import AddPaymentScreen from '../screens/account/AddPaymentScreen';
import { MainTabNavigator } from './MainTabNavigator';

const Stack = createStackNavigator<RootStackParamList>();

export const RootNavigator = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Welcome"
        screenOptions={{
          headerShown: false,
          cardStyle: { backgroundColor: '#FFFFFF' },
        }}
      >
        {/* 认证流程 */}
        <Stack.Screen name="Welcome" component={WelcomeScreen} />
        <Stack.Screen name="EmailLogin" component={EmailLoginScreen} />
        <Stack.Screen name="EmailRegister" component={EmailRegisterScreen} />
        <Stack.Screen name="EmailVerification" component={EmailVerificationScreen} />
        <Stack.Screen name="VerificationSuccess" component={VerificationSuccessScreen} />
        <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
        <Stack.Screen name="ResetPassword" component={ResetPasswordScreen} />
        
        {/* 主应用 */}
        <Stack.Screen name="LocationPermission" component={LocationPermissionScreen} />
        <Stack.Screen name="MainTabs" component={MainTabNavigator} />
        <Stack.Screen name="StationDetail" component={StationDetailScreen} />
        <Stack.Screen name="ChargingProcess" component={ChargingProcessScreen} />
        <Stack.Screen name="ChargingComplete" component={ChargingCompleteScreen} />
        <Stack.Screen name="ChargingHistory" component={ChargingHistoryScreen} />
        <Stack.Screen name="ChargingHistoryDetail" component={ChargingHistoryDetailScreen} />
        <Stack.Screen name="PersonalInfo" component={PersonalInfoScreen} />
        <Stack.Screen name="PaymentMethods" component={PaymentMethodsScreen} />
        <Stack.Screen name="AddPayment" component={AddPaymentScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
};
