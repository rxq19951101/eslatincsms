/**
 * 忘记密码页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  StatusBar,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { sendResetPasswordEmail } from '../../api/auth';

type ForgotPasswordScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'ForgotPassword'
>;

const ForgotPasswordScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<ForgotPasswordScreenNavigationProp>();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const handleSendResetLink = async () => {
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

    setIsLoading(true);
    try {
      await sendResetPasswordEmail(email.trim().toLowerCase());
      setEmailSent(true);
    } catch (error: any) {
      Alert.alert(t.common.error, error.message || t.auth.resetFailed);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBackToLogin = () => {
    navigation.goBack();
  };

  if (emailSent) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.content}>
          <View style={styles.successContainer}>
            <View style={styles.iconCircle}>
              <Text style={styles.icon}>✉️</Text>
            </View>
            <Text style={styles.successTitle}>Email Sent!</Text>
            <Text style={styles.successSubtitle}>
              Check your email for a link to reset your password.
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={handleBackToLogin}
              activeOpacity={0.8}
            >
              <Text style={styles.primaryButtonText}>{t.auth.backToSignIn}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        {/* 返回按钮 */}
        <TouchableOpacity style={styles.backButton} onPress={handleBackToLogin}>
          <Text style={styles.backButtonText}>←</Text>
        </TouchableOpacity>

        {/* 标题 */}
        <View style={styles.header}>
          <Text style={styles.title}>Forgot Password? 🔑</Text>
          <Text style={styles.subtitle}>
            Enter your email and we'll send you a link to reset your password
          </Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 邮箱输入 */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Email</Text>
            <TextInput
              style={styles.input}
              placeholder="your.email@example.com"
              placeholderTextColor={COLORS.TEXT_SECONDARY}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              editable={!isLoading}
            />
          </View>

          {/* 发送按钮 */}
          <TouchableOpacity
            style={[styles.sendButton, isLoading && styles.sendButtonDisabled]}
            onPress={handleSendResetLink}
            disabled={isLoading}
            activeOpacity={0.8}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.sendButtonText}>Send Reset Link</Text>
            )}
          </TouchableOpacity>

          {/* 返回登录链接 */}
          <TouchableOpacity
            style={styles.backLinkContainer}
            onPress={handleBackToLogin}
            disabled={isLoading}
          >
            <Text style={styles.backLinkText}>← {t.auth.backToSignIn}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
  },
  backButton: {
    marginTop: 20,
    width: 40,
    height: 40,
    justifyContent: 'center',
  },
  backButtonText: {
    fontSize: 28,
    color: COLORS.TEXT_PRIMARY,
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
    lineHeight: 24,
  },
  form: {
    flex: 1,
  },
  inputContainer: {
    marginBottom: 24,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: COLORS.TEXT_PRIMARY,
  },
  sendButton: {
    backgroundColor: COLORS.PRIMARY,
    paddingVertical: 16,
    borderRadius: 25,
    alignItems: 'center',
    marginBottom: 24,
    shadowColor: COLORS.PRIMARY,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  sendButtonDisabled: {
    opacity: 0.6,
  },
  sendButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  backLinkContainer: {
    alignItems: 'center',
  },
  backLinkText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  successContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  iconCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.PRIMARY + '20',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 32,
  },
  icon: {
    fontSize: 60,
  },
  successTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 12,
    textAlign: 'center',
  },
  successSubtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: 40,
    lineHeight: 24,
  },
  primaryButton: {
    backgroundColor: COLORS.PRIMARY,
    paddingVertical: 16,
    paddingHorizontal: 40,
    borderRadius: 25,
    alignItems: 'center',
    shadowColor: COLORS.PRIMARY,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default ForgotPasswordScreen;
