/**
 * 忘记密码页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { sendResetPasswordEmail } from '../../api/auth';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';

type ForgotPasswordScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'ForgotPassword'
>;

const ForgotPasswordScreen = () => {
  const { t, locale } = useI18n();

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
      await sendResetPasswordEmail(email.trim().toLowerCase(), locale);
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
      <Screen>
        <StatusBar barStyle="dark-content" />
        <View style={styles.content}>
          <View style={styles.successContainer}>
            <Text style={styles.successTitle}>{t.auth.resetSentTitle}</Text>
            <Text style={styles.successSubtitle}>{t.auth.resetSentBody}</Text>
            <Button title={t.auth.backToSignIn} onPress={handleBackToLogin} size="large" />
          </View>
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <StatusBar barStyle="dark-content" />
      <ScreenHeader title="" onBack={handleBackToLogin} />

      <View style={styles.content}>
        {/* 标题 */}
        <View style={styles.header}>
          <Text style={styles.title}>{t.auth.forgotTitle}</Text>
          <Text style={styles.subtitle}>{t.auth.forgotSubtitle}</Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
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

          {/* 发送按钮 */}
          <Button
            title={t.auth.sendReset}
            onPress={handleSendResetLink}
            disabled={isLoading}
            loading={isLoading}
            size="large"
          />

          {/* 返回登录链接 */}
          <Button title={t.auth.backToSignIn} variant="text" onPress={handleBackToLogin} disabled={isLoading} />
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
    lineHeight: 24,
  },
  form: {
    flex: 1,
  },
  inputContainer: {
    marginBottom: 24,
  },
  successContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
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
});

export default ForgotPasswordScreen;
