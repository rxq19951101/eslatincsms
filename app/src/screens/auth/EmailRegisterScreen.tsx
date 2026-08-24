/**
 * 邮箱注册页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  StatusBar,
  Alert,
  ScrollView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, PASSWORD_RULES } from '../../constants/config';
import { useI18n } from '../../i18n';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { registerWithEmail } from '../../store/slices/authSlice';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import Icon from '../../components/ui/Icon';

type EmailRegisterScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'EmailRegister'
>;

const EmailRegisterScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<EmailRegisterScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { isLoading } = useAppSelector((state) => state.auth);

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [agreeToTerms, setAgreeToTerms] = useState(false);

  /**
   * 计算密码强度
   */
  const calculatePasswordStrength = (pwd: string): number => {
    let strength = 0;
    if (pwd.length >= PASSWORD_RULES.MIN_LENGTH) strength++;
    if (PASSWORD_RULES.REQUIRE_UPPERCASE && /[A-Z]/.test(pwd)) strength++;
    if (PASSWORD_RULES.REQUIRE_LOWERCASE && /[a-z]/.test(pwd)) strength++;
    if (PASSWORD_RULES.REQUIRE_NUMBER && /[0-9]/.test(pwd)) strength++;
    if (PASSWORD_RULES.REQUIRE_SPECIAL && /[!@#$%^&*(),.?":{}|<>]/.test(pwd)) strength++;
    return strength;
  };

  const passwordStrength = calculatePasswordStrength(password);

  const getStrengthColor = () => {
    if (passwordStrength <= 1) return COLORS.ERROR;
    if (passwordStrength <= 2) return COLORS.WARNING;
    if (passwordStrength <= 3) return COLORS.SUCCESS;
    return COLORS.PRIMARY;
  };

  const getStrengthText = () => {
    if (passwordStrength <= 1) return t.auth.strengthWeak;
    if (passwordStrength <= 2) return t.auth.strengthFair;
    if (passwordStrength <= 3) return t.auth.strengthGood;
    return t.auth.strengthStrong;
  };

  const handleRegister = async () => {
    // 验证全名
    if (!fullName.trim()) {
      Alert.alert(t.common.error, t.auth.enterFullName);
      return;
    }

    // 验证邮箱
    if (!email.trim()) {
      Alert.alert(t.common.error, t.auth.enterEmail);
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      Alert.alert(t.common.error, t.auth.invalidEmail);
      return;
    }

    // 验证密码
    if (password.length < PASSWORD_RULES.MIN_LENGTH) {
      Alert.alert(t.common.error, t.auth.passwordMin.replace('{n}', String(PASSWORD_RULES.MIN_LENGTH)));
      return;
    }
    if (PASSWORD_RULES.REQUIRE_UPPERCASE && !/[A-Z]/.test(password)) {
      Alert.alert(t.common.error, t.auth.passwordUpper);
      return;
    }
    if (PASSWORD_RULES.REQUIRE_LOWERCASE && !/[a-z]/.test(password)) {
      Alert.alert(t.common.error, t.auth.passwordLower);
      return;
    }
    if (PASSWORD_RULES.REQUIRE_NUMBER && !/[0-9]/.test(password)) {
      Alert.alert(t.common.error, t.auth.passwordNumber);
      return;
    }

    // 验证密码确认
    if (password !== confirmPassword) {
      Alert.alert(t.common.error, t.auth.passwordMismatch);
      return;
    }

    // 验证是否同意条款
    if (!agreeToTerms) {
      Alert.alert(t.common.error, t.auth.agreeTerms);
      return;
    }

    try {
      await dispatch(
        registerWithEmail({
          email: email.trim().toLowerCase(),
          password,
          full_name: fullName.trim(),
        })
      ).unwrap();

      // 注册成功，导航到邮箱验证页面
      navigation.navigate('EmailVerification', { email: email.trim().toLowerCase() });
    } catch (err: any) {
      Alert.alert(t.auth.loginFailed, err.message || t.common.error);
    }
  };

  const handleSignInNavigation = () => {
    navigation.navigate('EmailLogin');
  };

  const handleBackToWelcome = () => {
    navigation.goBack();
  };

  return (
    <Screen>
      <StatusBar barStyle="dark-content" />
      <ScreenHeader title="" onBack={handleBackToWelcome} />

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* 标题 */}
        <View style={styles.header}>
          <Text style={styles.title}>{t.auth.signUp}</Text>
          <Text style={styles.subtitle}>{t.auth.signUpSubtitle}</Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 全名输入 */}
          <View style={styles.inputContainer}>
            <TextField
              label={t.auth.fullName}
              placeholder={t.auth.fullNamePlaceholder}
              value={fullName}
              onChangeText={setFullName}
              autoCapitalize="words"
              editable={!isLoading}
            />
          </View>

          {/* 邮箱输入 */}
          <View style={styles.inputContainer}>
            <TextField
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
                inputStyle={styles.passwordInput}
                placeholder={t.auth.enterPassword}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
                accessibilityLabel={showPassword ? t.auth.hidePassword : t.auth.showPassword}
                accessibilityRole="button"
                style={styles.eyeButton}
                onPress={() => setShowPassword(!showPassword)}
              >
                <Icon name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>
            
            {/* 密码强度指示器 */}
            {password.length > 0 && (
              <View style={styles.strengthContainer}>
                <View style={styles.strengthBar}>
                  <View
                    style={[
                      styles.strengthProgress,
                      {
                        width: `${(passwordStrength / 4) * 100}%`,
                        backgroundColor: getStrengthColor(),
                      },
                    ]}
                  />
                </View>
                <Text style={[styles.strengthText, { color: getStrengthColor() }]}>
                  {getStrengthText()}
                </Text>
              </View>
            )}
          </View>

          {/* 确认密码输入 */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>{t.auth.confirmPassword}</Text>
            <View style={styles.passwordContainer}>
              <TextField
                inputStyle={styles.passwordInput}
                placeholder={t.auth.confirmPassword}
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry={!showConfirmPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
                accessibilityLabel={showConfirmPassword ? t.auth.hidePassword : t.auth.showPassword}
                accessibilityRole="button"
                style={styles.eyeButton}
                onPress={() => setShowConfirmPassword(!showConfirmPassword)}
              >
                <Icon name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>
          </View>

          {/* 同意条款 */}
          <TouchableOpacity
            style={styles.termsContainer}
            onPress={() => setAgreeToTerms(!agreeToTerms)}
            disabled={isLoading}
          >
            <View style={[styles.checkbox, agreeToTerms && styles.checkboxChecked]}>
              {agreeToTerms && <Icon name="checkmark" size={14} color={COLORS.IOS_WHITE} />}
            </View>
            <Text style={styles.termsText}>
              {t.auth.termsPrefix}{' '}
              <Text style={styles.termsLink}>{t.auth.termsLink}</Text>
            </Text>
          </TouchableOpacity>

          {/* 注册按钮 */}
          <Button
            title={t.auth.signUp}
            onPress={handleRegister}
            disabled={isLoading}
            loading={isLoading}
            size="large"
          />

          {/* 已有账号链接 */}
          <View style={styles.signinContainer}>
            <Text style={styles.signinText}>{t.auth.hasAccount} </Text>
            <TouchableOpacity onPress={handleSignInNavigation} disabled={isLoading}>
              <Text style={styles.signinLink}>{t.auth.signIn}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </Screen>
  );
};

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 24,
    paddingBottom: 40,
  },
  header: {
    marginTop: 20,
    marginBottom: 32,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
  },
  form: {
    flex: 1,
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
  strengthContainer: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
  strengthBar: {
    flex: 1,
    height: 4,
    backgroundColor: COLORS.BORDER,
    borderRadius: 2,
    marginRight: 12,
    overflow: 'hidden',
  },
  strengthProgress: {
    height: '100%',
    borderRadius: 2,
  },
  strengthText: {
    fontSize: 12,
    fontWeight: '600',
  },
  termsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 24,
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
  checkmark: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: 'bold',
  },
  termsText: {
    fontSize: 14,
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
  },
  termsLink: {
    color: COLORS.PRIMARY,
    fontWeight: '600',
  },
  signinContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  signinText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  signinLink: {
    color: COLORS.PRIMARY,
    fontSize: 14,
    fontWeight: '600',
  },
});

export default EmailRegisterScreen;
