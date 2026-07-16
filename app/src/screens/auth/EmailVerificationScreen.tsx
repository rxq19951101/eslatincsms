/**
 * 邮箱验证：输入 6 位验证码 / 重发邮件
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  Alert,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { resendVerificationEmail, verifyEmailWithCode } from '../../api/auth';
import { useDispatch } from 'react-redux';
import type { AppDispatch } from '../../store';
import { setUser } from '../../store/slices/authSlice';
import Screen from '../../components/ui/Screen';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';

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
    <Screen edges={['top', 'bottom']}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        <View style={styles.textContainer}>
          <Text style={styles.title}>{t.auth.verifyTitle}</Text>
          <Text style={styles.subtitle}>{t.auth.verifySentTo}</Text>
          <Text style={styles.email}>{email}</Text>
          <Text style={styles.instruction}>{t.auth.verifyBody}</Text>

          <TextField
            inputStyle={styles.codeInput}
            value={code}
            onChangeText={setCode}
            placeholder={t.auth.enterCode}
            keyboardType="number-pad"
            maxLength={8}
            autoFocus
            textContentType="oneTimeCode"
          />
        </View>

        <View style={styles.buttonsContainer}>
          <Button
            title={t.auth.verifyButton}
            onPress={handleVerify}
            disabled={isVerifying}
            loading={isVerifying}
            size="large"
          />

          <Button
            title={countdown > 0 ? `${t.auth.resendEmail} (${countdown}s)` : t.auth.resendEmail}
            onPress={handleResendEmail}
            disabled={countdown > 0 || isResending}
            loading={isResending}
            variant="outline"
          />

          <Button title={t.auth.changeEmail} variant="text" onPress={handleChangeEmail} />
          <Button title={t.auth.backToSignIn} variant="text" onPress={handleBackToLogin} />
        </View>
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: {
    flex: 1,
    paddingHorizontal: 24,
    paddingVertical: 40,
    justifyContent: 'space-between',
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
});

export default EmailVerificationScreen;
