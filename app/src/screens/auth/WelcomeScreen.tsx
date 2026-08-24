/**
 * 欢迎页面 — 拉美首发：仅邮箱登录/注册
 */

import React from 'react';
import { View, Text, StyleSheet, StatusBar, TouchableOpacity, useWindowDimensions } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';
import BrandLogo from '../../components/brand/BrandLogo';
import { spacing, typography } from '../../theme';

type WelcomeScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Welcome'>;

const WelcomeScreen = () => {
  const { t } = useI18n();
  const { width, height } = useWindowDimensions();

  const navigation = useNavigation<WelcomeScreenNavigationProp>();
  const compact = width < 360 || height < 700;

  return (
    <Screen testID="welcome-screen" edges={['top', 'bottom']} style={styles.screen}>
      <StatusBar barStyle="dark-content" backgroundColor={COLORS.BACKGROUND} />

      <View style={styles.content}>
        <View style={styles.logoContainer}>
          <BrandLogo
            testID="welcome-brand-logo"
            style={[styles.logo, compact && styles.logoCompact]}
          />
          <Text style={styles.tagline}>{t.tagline}</Text>
        </View>

        <View style={styles.buttonsContainer}>
          <Button
            testID="welcome-email-sign-in"
            accessibilityLabel={t.auth.signInEmail}
            title={t.auth.signInEmail}
            onPress={() => navigation.navigate('EmailLogin')}
            size="large"
            style={styles.primaryButton}
          />

          <View style={styles.signupContainer}>
            <Text style={styles.signupText}>{t.auth.noAccount} </Text>
            <TouchableOpacity
              testID="welcome-email-register"
              accessibilityRole="button"
              accessibilityLabel={t.auth.signUp}
              onPress={() => navigation.navigate('EmailRegister')}
            >
              <Text style={styles.signupLink}>{t.auth.signUp}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  screen: {
    backgroundColor: COLORS.CARD_BG,
  },
  content: {
    flex: 1,
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingTop: spacing.md,
    paddingBottom: spacing.xl,
    width: '100%',
    maxWidth: 480,
    alignSelf: 'center',
  },
  logoContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logo: {
    width: 260,
    height: 260,
  },
  logoCompact: {
    width: 220,
    height: 220,
  },
  tagline: {
    fontSize: typography.label,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    lineHeight: 24,
    maxWidth: 320,
    marginTop: spacing.sm,
  },
  buttonsContainer: {
    width: '100%',
    paddingTop: spacing.lg,
  },
  primaryButton: {
    borderRadius: 14,
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
    fontWeight: typography.semibold,
  },
});

export default WelcomeScreen;
