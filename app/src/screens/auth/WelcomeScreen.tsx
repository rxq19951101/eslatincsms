/**
 * 欢迎页面 — 拉美首发：仅邮箱登录/注册
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';
import { palette, spacing, typography } from '../../theme';

type WelcomeScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Welcome'>;

const WelcomeScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<WelcomeScreenNavigationProp>();

  return (
    <Screen edges={['top', 'bottom']}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        <View style={styles.logoContainer}>
          <Text style={styles.wordmark}>ESLATIN</Text>
          <Text style={styles.appName}>{t.appName}</Text>
          <Text style={styles.tagline}>{t.tagline}</Text>
        </View>

        <View style={styles.buttonsContainer}>
          <Button
            title={t.auth.signInEmail}
            onPress={() => navigation.navigate('EmailLogin')}
            size="large"
          />

          <View style={styles.signupContainer}>
            <Text style={styles.signupText}>{t.auth.noAccount} </Text>
            <Text onPress={() => navigation.navigate('EmailRegister')}>
              <Text style={styles.signupLink}>{t.auth.signUp}</Text>
            </Text>
          </View>
        </View>
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: {
    flex: 1,
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 40,
  },
  logoContainer: {
    alignItems: 'center',
    marginTop: 60,
  },
  wordmark: {
    fontSize: 13,
    fontWeight: typography.bold,
    letterSpacing: 2.4,
    color: palette.brand,
    marginBottom: spacing.lg,
  },
  appName: {
    fontSize: 32,
    fontWeight: typography.bold,
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  tagline: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
  },
  buttonsContainer: {
    width: '100%',
  },
  signupContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  signupText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  signupLink: {
    color: COLORS.PRIMARY,
    fontSize: 14,
    fontWeight: '600',
  },
});

export default WelcomeScreen;
