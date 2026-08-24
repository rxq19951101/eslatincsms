/**
 * 邮箱登录页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  StatusBar,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { loginWithEmail, clearError } from '../../store/slices/authSlice';
import { saveRememberMe } from '../../utils/tokenManager';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import Icon from '../../components/ui/Icon';
import BrandLogo from '../../components/brand/BrandLogo';

type EmailLoginScreenNavigationProp = StackNavigationProp<RootStackParamList, 'EmailLogin'>;

const EmailLoginScreen = () => {
  const { t, locale } = useI18n();

  const navigation = useNavigation<EmailLoginScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { isLoading, error } = useAppSelector((state) => state.auth);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleLogin = async () => {
    // 验证输入
    if (!email.trim()) {
      Alert.alert(t.common.error, t.auth.enterEmail);
      return;
    }
    if (!password) {
      Alert.alert(t.common.error, t.auth.enterPassword);
      return;
    }

    // 验证邮箱格式
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      Alert.alert(t.common.error, t.auth.invalidEmail);
      return;
    }

    try {
      // 保存记住我状态
      await saveRememberMe(rememberMe);

      // 调用登录API
      await dispatch(
        loginWithEmail({
          email: email.trim().toLowerCase(),
          password,
          remember_me: rememberMe,
        })
      ).unwrap();

      // 登录成功，导航到位置权限页面
      navigation.navigate('LocationPermission');
    } catch (err: any) {
      const msg = err?.message || t.common.error;
      if (String(msg).toLowerCase().includes('email not verified')) {
        navigation.navigate('EmailVerification', { email: email.trim().toLowerCase() });
        return;
      }
      Alert.alert(
        t.auth.loginFailed,
        msg,
        [{ text: t.common.ok }]
      );
    }
  };

  const handleForgotPassword = () => {
    navigation.navigate('ForgotPassword');
  };

  const handleBackToWelcome = () => {
    dispatch(clearError());
    navigation.goBack();
  };

  return (
    <Screen style={styles.screen}>
      <StatusBar barStyle="dark-content" backgroundColor={COLORS.CARD_BG} />
      <ScreenHeader
        title=""
        onBack={handleBackToWelcome}
        backTestID="app-login-back"
        style={styles.screenHeader}
        right={
          <TouchableOpacity
            testID="app-login-language"
            accessibilityRole="button"
            accessibilityLabel={t.account.language}
            style={styles.languageTrigger}
            onPress={() => navigation.navigate('Language')}
          >
            <Icon name="globe-outline" size={18} color={COLORS.PRIMARY_DARK} />
            <Text style={styles.languageCode}>{locale.toUpperCase()}</Text>
            <Icon name="chevron-forward" size={14} color={COLORS.TEXT_TERTIARY} />
          </TouchableOpacity>
        }
      />
      <View style={styles.content}>
        <View style={styles.brandContainer}>
          <BrandLogo testID="app-login-brand-logo" style={styles.brandLogo} />
        </View>

        {/* 标题 */}
        <View style={styles.header}>
          <Text style={styles.title}>{t.auth.hello}</Text>
          <Text style={styles.subtitle}>{t.auth.signInSubtitle}</Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 邮箱输入 */}
          <View style={styles.inputContainer}>
            <TextField
              testID="app-login-email"
              accessibilityLabel={t.auth.email}
              label={t.auth.email}
              placeholder={t.auth.emailPlaceholder}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              editable={!isLoading}
            />
          </View>

          {/* 密码输入 */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>{t.auth.password}</Text>
            <View style={styles.passwordContainer}>
              <TextField
                testID="app-login-password"
                accessibilityLabel={t.auth.password}
                inputStyle={styles.passwordInput}
                placeholder={t.auth.password}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
                testID="app-login-password-toggle"
                accessibilityLabel={showPassword ? t.auth.hidePassword : t.auth.showPassword}
                accessibilityRole="button"
                style={styles.eyeButton}
                onPress={() => setShowPassword(!showPassword)}
              >
                <Icon name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>
          </View>

          {/* 记住我 & 忘记密码 */}
          <View style={styles.optionsRow}>
            <TouchableOpacity
              testID="app-login-remember"
              accessibilityLabel={t.auth.rememberMe}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: rememberMe, disabled: isLoading }}
              style={styles.rememberMeContainer}
              onPress={() => setRememberMe(!rememberMe)}
              disabled={isLoading}
            >
              <View style={[styles.checkbox, rememberMe && styles.checkboxChecked]}>
                {rememberMe && <Icon name="checkmark" size={14} color={COLORS.IOS_WHITE} />}
              </View>
              <Text style={styles.rememberMeText}>{t.auth.rememberMe}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              testID="app-login-forgot-password"
              accessibilityLabel={t.auth.forgotPassword}
              accessibilityRole="button"
              onPress={handleForgotPassword}
              disabled={isLoading}
            >
              <Text style={styles.forgotPasswordText}>{t.auth.forgotPassword}</Text>
            </TouchableOpacity>
          </View>

          {/* 错误提示 */}
          {error && (
            <View testID="app-login-error" accessibilityRole="alert" style={styles.errorContainer}>
              <Text style={styles.errorText}>{error.message}</Text>
            </View>
          )}

          {/* 登录按钮 */}
          <Button
            testID="app-login-submit"
            accessibilityLabel={t.auth.signIn}
            title={t.auth.signIn}
            onPress={handleLogin}
            disabled={isLoading}
            loading={isLoading}
            size="large"
          />
        </View>
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  screen: {
    backgroundColor: COLORS.CARD_BG,
  },
  screenHeader: {
    backgroundColor: COLORS.CARD_BG,
  },
  languageTrigger: {
    height: 36,
    paddingHorizontal: 10,
    borderRadius: 18,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.PRIMARY_SOFT,
  },
  languageCode: {
    marginHorizontal: 6,
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.PRIMARY_DARK,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    width: '100%',
    maxWidth: 480,
    alignSelf: 'center',
  },
  brandContainer: {
    alignItems: 'center',
    marginTop: -16,
  },
  brandLogo: {
    width: 168,
    height: 168,
  },
  header: {
    alignItems: 'center',
    marginTop: -18,
    marginBottom: 28,
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
  },
  form: {
    width: '100%',
  },
  inputContainer: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  passwordContainer: {
    position: 'relative',
  },
  passwordInput: {
    paddingRight: 50,
  },
  eyeButton: {
    position: 'absolute',
    right: 16,
    top: 14,
    padding: 4,
  },
  optionsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  rememberMeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  checkbox: {
    width: 20,
    height: 20,
    borderWidth: 2,
    borderColor: COLORS.BORDER,
    borderRadius: 4,
    marginRight: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxChecked: {
    backgroundColor: COLORS.PRIMARY,
    borderColor: COLORS.PRIMARY,
  },
  rememberMeText: {
    fontSize: 14,
    color: COLORS.TEXT_PRIMARY,
  },
  forgotPasswordText: {
    fontSize: 14,
    color: COLORS.PRIMARY,
    fontWeight: '600',
  },
  errorContainer: {
    backgroundColor: '#FEE2E2',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: COLORS.ERROR,
    fontSize: 14,
  },
});

export default EmailLoginScreen;
