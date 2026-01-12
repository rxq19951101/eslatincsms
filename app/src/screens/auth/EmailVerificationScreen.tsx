/**
 * 邮箱验证等待页面
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  StatusBar,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { resendVerificationEmail } from '../../api/auth';

type EmailVerificationScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'EmailVerification'
>;
type EmailVerificationScreenRouteProp = RouteProp<RootStackParamList, 'EmailVerification'>;

const EmailVerificationScreen = () => {
  const navigation = useNavigation<EmailVerificationScreenNavigationProp>();
  const route = useRoute<EmailVerificationScreenRouteProp>();
  const { email } = route.params;

  const [countdown, setCountdown] = useState(60);
  const [isResending, setIsResending] = useState(false);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleResendEmail = async () => {
    if (countdown > 0) return;

    setIsResending(true);
    try {
      await resendVerificationEmail(email);
      Alert.alert('Success', 'Verification email has been resent');
      setCountdown(60);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to resend email');
    } finally {
      setIsResending(false);
    }
  };

  const handleChangeEmail = () => {
    navigation.goBack();
  };

  const handleBackToLogin = () => {
    navigation.navigate('EmailLogin');
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        {/* 邮件图标 */}
        <View style={styles.iconContainer}>
          <View style={styles.iconCircle}>
            <Text style={styles.icon}>📧</Text>
          </View>
        </View>

        {/* 标题和说明 */}
        <View style={styles.textContainer}>
          <Text style={styles.title}>Verify Your Email 🔒</Text>
          <Text style={styles.subtitle}>
            We have sent a verification link to your email:
          </Text>
          <Text style={styles.email}>{email}</Text>
          <Text style={styles.instruction}>
            Please click the link in your email to verify your account.
          </Text>
          <Text style={styles.note}>
            💡 Check your spam folder if you don't see the email.
          </Text>
        </View>

        {/* 按钮组 */}
        <View style={styles.buttonsContainer}>
          {/* 重新发送按钮 */}
          <TouchableOpacity
            style={[styles.resendButton, countdown > 0 && styles.resendButtonDisabled]}
            onPress={handleResendEmail}
            disabled={countdown > 0 || isResending}
            activeOpacity={0.8}
          >
            {isResending ? (
              <ActivityIndicator color={COLORS.PRIMARY} />
            ) : (
              <Text
                style={[
                  styles.resendButtonText,
                  countdown > 0 && styles.resendButtonTextDisabled,
                ]}
              >
                {countdown > 0 ? `Resend Email (${countdown}s)` : 'Resend Email'}
              </Text>
            )}
          </TouchableOpacity>

          {/* 更改邮箱 */}
          <TouchableOpacity onPress={handleChangeEmail}>
            <Text style={styles.changeEmailText}>Change Email</Text>
          </TouchableOpacity>

          {/* 返回登录 */}
          <TouchableOpacity
            style={styles.backToLoginButton}
            onPress={handleBackToLogin}
            activeOpacity={0.8}
          >
            <Text style={styles.backToLoginText}>Back to Sign In</Text>
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
    paddingVertical: 40,
    justifyContent: 'space-between',
  },
  iconContainer: {
    alignItems: 'center',
    marginTop: 40,
  },
  iconCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.PRIMARY + '20',
    justifyContent: 'center',
    alignItems: 'center',
  },
  icon: {
    fontSize: 60,
  },
  textContainer: {
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 16,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: 8,
  },
  email: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.PRIMARY,
    marginBottom: 16,
    textAlign: 'center',
  },
  instruction: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: 16,
    lineHeight: 20,
  },
  note: {
    fontSize: 13,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    fontStyle: 'italic',
  },
  buttonsContainer: {
    width: '100%',
  },
  resendButton: {
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    borderColor: COLORS.PRIMARY,
    paddingVertical: 14,
    borderRadius: 25,
    alignItems: 'center',
    marginBottom: 16,
  },
  resendButtonDisabled: {
    borderColor: COLORS.DISABLED,
  },
  resendButtonText: {
    color: COLORS.PRIMARY,
    fontSize: 16,
    fontWeight: '600',
  },
  resendButtonTextDisabled: {
    color: COLORS.DISABLED,
  },
  changeEmailText: {
    color: COLORS.PRIMARY,
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
    marginBottom: 16,
  },
  backToLoginButton: {
    paddingVertical: 14,
    alignItems: 'center',
  },
  backToLoginText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
});

export default EmailVerificationScreen;
