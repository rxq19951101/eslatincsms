/**
 * 根导航 — 根据登录态决定初始路由
 */
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import type { RootStackParamList } from '../types';
import { useAppSelector } from '../hooks/useRedux';
import { navigationRef } from './navigationRef';
import { linking } from './linking';

import WelcomeScreen from '../screens/auth/WelcomeScreen';
import EmailLoginScreen from '../screens/auth/EmailLoginScreen';
import EmailRegisterScreen from '../screens/auth/EmailRegisterScreen';
import EmailVerificationScreen from '../screens/auth/EmailVerificationScreen';
import VerificationSuccessScreen from '../screens/auth/VerificationSuccessScreen';
import ForgotPasswordScreen from '../screens/auth/ForgotPasswordScreen';
import ResetPasswordScreen from '../screens/auth/ResetPasswordScreen';

import LocationPermissionScreen from '../screens/home/LocationPermissionScreen';
import StationDetailScreen from '../screens/home/StationDetailScreen';
import ChargingProcessScreen from '../screens/charging/ChargingProcessScreen';
import ChargingCompleteScreen from '../screens/charging/ChargingCompleteScreen';
import ChargingHistoryScreen from '../screens/charging/ChargingHistoryScreen';
import ChargingHistoryDetailScreen from '../screens/charging/ChargingHistoryDetailScreen';
import PersonalInfoScreen from '../screens/account/PersonalInfoScreen';
import PaymentMethodsScreen from '../screens/account/PaymentMethodsScreen';
import AddPaymentScreen from '../screens/account/AddPaymentScreen';
import PaymentHubScreen from '../screens/payment/PaymentHubScreen';
import WompiPaymentScreen from '../screens/payment/WompiPaymentScreen';
import MercadoPagoPaymentScreen from '../screens/payment/MercadoPagoPaymentScreen';
import PaymentResultScreen from '../screens/payment/PaymentResultScreen';
import UnpaidBillsScreen from '../screens/wallet/UnpaidBillsScreen';
import HelpCenterScreen from '../screens/account/HelpCenterScreen';
import PrivacyPolicyScreen from '../screens/account/PrivacyPolicyScreen';
import AboutScreen from '../screens/account/AboutScreen';
import LanguageSettingsScreen from '../screens/account/LanguageSettingsScreen';
import { MainTabNavigator } from './MainTabNavigator';

const Stack = createStackNavigator<RootStackParamList>();

export const RootNavigator = () => {
  const { isAuthenticated, isInitialized } = useAppSelector((s) => s.auth);

  if (!isInitialized) {
    return null;
  }

  return (
    <NavigationContainer ref={navigationRef} linking={linking}>
      <Stack.Navigator
        initialRouteName={isAuthenticated ? 'MainTabs' : 'Welcome'}
        screenOptions={{
          headerShown: false,
          cardStyle: { backgroundColor: '#FFFFFF' },
        }}
      >
        <Stack.Screen name="Welcome" component={WelcomeScreen} />
        <Stack.Screen name="EmailLogin" component={EmailLoginScreen} />
        <Stack.Screen name="EmailRegister" component={EmailRegisterScreen} />
        <Stack.Screen name="EmailVerification" component={EmailVerificationScreen} />
        <Stack.Screen name="VerificationSuccess" component={VerificationSuccessScreen} />
        <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
        <Stack.Screen name="ResetPassword" component={ResetPasswordScreen} />

        <Stack.Screen name="LocationPermission" component={LocationPermissionScreen} />
        <Stack.Screen name="MainTabs" component={MainTabNavigator} />
        <Stack.Screen name="StationDetail" component={StationDetailScreen} />
        <Stack.Screen name="ChargingProcess" component={ChargingProcessScreen} />
        <Stack.Screen name="ChargingComplete" component={ChargingCompleteScreen} />
        <Stack.Screen name="ChargingHistory" component={ChargingHistoryScreen} />
        <Stack.Screen name="ChargingHistoryDetail" component={ChargingHistoryDetailScreen} />
        <Stack.Screen name="PersonalInfo" component={PersonalInfoScreen} />
        <Stack.Screen name="Language" component={LanguageSettingsScreen} />
        <Stack.Screen name="PaymentHub" component={PaymentHubScreen} />
        <Stack.Screen name="PaymentMethods" component={PaymentMethodsScreen} />
        <Stack.Screen name="AddPayment" component={AddPaymentScreen} />
        <Stack.Screen name="UnpaidBills" component={UnpaidBillsScreen} />
        <Stack.Screen name="HelpCenter" component={HelpCenterScreen} />
        <Stack.Screen name="PrivacyPolicy" component={PrivacyPolicyScreen} />
        <Stack.Screen name="About" component={AboutScreen} />
        <Stack.Screen name="WompiPayment" component={WompiPaymentScreen} options={{ presentation: 'modal' }} />
        <Stack.Screen name="MercadoPagoPayment" component={MercadoPagoPaymentScreen} options={{ presentation: 'modal' }} />
        <Stack.Screen name="PaymentResult" component={PaymentResultScreen} options={{ presentation: 'modal' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
};
