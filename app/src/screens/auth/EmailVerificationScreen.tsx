/**
 * 邮箱验证：输入 6 位验证码 / 重发邮件
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
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { resendVerificationEmail, verifyEmailWithCode } from '../../api/auth';
import { useDispatch } from 'react-redux';
import type { AppDispatch } from '../../store';
import { setUser } from '../../store/slices/authSlice';

type EmailVerificationScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'EmailVerification'
>;
type EmailVerificationScreenRouteProp = RouteProp<RootStackParamList, 'EmailVerification'>;

const EmailVerificationScreen = () => {
  const { t } = useI18n();
  const dispatch = useDispatch<AppDispatch>();

  const navigation = useNavigation<EmailVerificationScreenNavigationProp>();
  const route = useRoute<EmailVerificationScreenRouteProp>();
  const { email } = route.params;

  const [code, setCode] = useState('');
  const [countdown, setCountdown] = useState(60);
  const [isResending, setIsResending] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleVerify = async () => {
    const trimmed = code.trim();
    if (trimmed.length < 4) {
      Alert.alert(t.common.error, t.auth.codeRequired);
      return;
    }
    setIsVerifying(true);
    try {
      const result = await verifyEmailWithCode({ email, code: trimmed });
      dispatch(setUser(result.user));
      navigation.replace('VerificationSuccess');
    } catch (error: any) {
      Alert.alert(t.common.error, error.message || t.auth.verifyFailed);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleResendEmail = async () => {
    if (countdown > 0) return;

    setIsResending(true);
    try {
      await resendVerificationEmail(email);
      Alert.alert(t.common.success, t.auth.resendSuccess);
      setCountdown(60);
    } catch (error: any) {
      Alert.alert(t.common.error, error.message || t.auth.resendFailed);
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
        <View style={styles.iconContainer}>
          <View style={styles.iconCircle}>
            <Text style={styles.icon}>📧</Text>
          </View>
        </View>

        <View style={styles.textContainer}>
          <Text style={styles.title}>{t.auth.verifyTitle}</Text>
          <Text style={styles.subtitle}>{t.auth.verifySentTo}</Text>
          <Text style={styles.email}>{email}</Text>
          <Text style={styles.instruction}>{t.auth.verifyBody}</Text>

          <TextInput
            style={styles.codeInput}
            value={code}
            onChangeText={setCode}
            placeholder={t.auth.enterCode}
            placeholderTextColor={COLORS.TEXT_SECONDARY}
            keyboardType="number-pad"
            maxLength={8}
            autoFocus
            textContentType="oneTimeCode"
          />
        </View>

        <View style={styles.buttonsContainer}>
          <TouchableOpacity
            style={[styles.verifyButton, isVerifying && styles.verifyButtonDisabled]}
            onPress={handleVerify}
            disabled={isVerifying}
            activeOpacity={0.8}
          >
            {isVerifying ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.verifyButtonText}>{t.auth.verifyButton}</Text>
            )}
          </TouchableOpacity>

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
                {countdown > 0 ? `${t.auth.resendEmail} (${countdown}s)` : t.auth.resendEmail}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity onPress={handleChangeEmail}>
            <Text style={styles.changeEmailText}>{t.auth.changeEmail}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backToLoginButton}
            onPress={handleBackToLogin}
            activeOpacity={0.8}
          >
            <Text style={styles.backToLoginText}>{t.auth.backToSignIn}</Text>
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
    marginTop: 24,
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
    paddingHorizontal: 12,
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
    marginBottom: 20,
    lineHeight: 20,
  },
  codeInput: {
    width: '100%',
    borderWidth: 1,
    borderColor: COLORS.BORDER || '#E5E7EB',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 24,
    letterSpacing: 8,
    textAlign: 'center',
    color: COLORS.TEXT_PRIMARY,
    backgroundColor: '#FFFFFF',
  },
  buttonsContainer: {
    width: '100%',
  },
  verifyButton: {
    backgroundColor: COLORS.PRIMARY,
    paddingVertical: 14,
    borderRadius: 25,
    alignItems: 'center',
    marginBottom: 12,
  },
  verifyButtonDisabled: {
    opacity: 0.7,
  },
  verifyButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
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
