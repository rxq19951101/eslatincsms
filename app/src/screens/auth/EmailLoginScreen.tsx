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

type EmailLoginScreenNavigationProp = StackNavigationProp<RootStackParamList, 'EmailLogin'>;

const EmailLoginScreen = () => {
  const { t } = useI18n();

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
    <Screen>
      <StatusBar barStyle="dark-content" />
      <ScreenHeader title="" onBack={handleBackToWelcome} />
      <View style={styles.content}>
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
              label={t.auth.email}
              placeholder="your.email@example.com"
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
                placeholder={t.auth.password}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
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
              style={styles.rememberMeContainer}
              onPress={() => setRememberMe(!rememberMe)}
              disabled={isLoading}
            >
              <View style={[styles.checkbox, rememberMe && styles.checkboxChecked]}>
                {rememberMe && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.rememberMeText}>{t.auth.rememberMe}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={handleForgotPassword} disabled={isLoading}>
              <Text style={styles.forgotPasswordText}>{t.auth.forgotPassword}</Text>
            </TouchableOpacity>
          </View>

          {/* 错误提示 */}
          {error && (
            <View style={styles.errorContainer}>
              <Text style={styles.errorText}>{error.message}</Text>
            </View>
          )}

          {/* 登录按钮 */}
          <Button
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
  content: {
    flex: 1,
    paddingHorizontal: 24,
  },
  header: {
    marginTop: 20,
    marginBottom: 40,
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
  checkmark: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: 'bold',
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
