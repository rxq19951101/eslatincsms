/**
 * 重置密码页面
 * 通过邮件链接（Deep Link）进入
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
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, PASSWORD_RULES } from '../../constants/config';
import { useI18n } from '../../i18n';
import { confirmResetPassword } from '../../api/auth';
import Screen from '../../components/ui/Screen';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import Icon from '../../components/ui/Icon';

type ResetPasswordScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'ResetPassword'
>;
type ResetPasswordScreenRouteProp = RouteProp<RootStackParamList, 'ResetPassword'>;

const ResetPasswordScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<ResetPasswordScreenNavigationProp>();
  const route = useRoute<ResetPasswordScreenRouteProp>();
  const { token } = route.params;

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  /**
   * 计算密码强度
   */
  const calculatePasswordStrength = (pwd: string): number => {
    let strength = 0;
    if (pwd.length >= PASSWORD_RULES.MIN_LENGTH) strength++;
    if (PASSWORD_RULES.REQUIRE_UPPERCASE && /[A-Z]/.test(pwd)) strength++;
    if (PASSWORD_RULES.REQUIRE_LOWERCASE && /[a-z]/.test(pwd)) strength++;
    if (PASSWORD_RULES.REQUIRE_NUMBER && /[0-9]/.test(pwd)) strength++;
    return strength;
  };

  const passwordStrength = calculatePasswordStrength(newPassword);

  const getStrengthColor = () => {
    if (passwordStrength <= 1) return COLORS.ERROR;
    if (passwordStrength === 2) return COLORS.WARNING;
    if (passwordStrength === 3) return COLORS.SUCCESS;
    return COLORS.PRIMARY;
  };

  const getStrengthText = () => {
    if (passwordStrength <= 1) return 'Weak';
    if (passwordStrength === 2) return 'Fair';
    if (passwordStrength === 3) return 'Good';
    return 'Strong';
  };

  const handleResetPassword = async () => {
    // 验证密码
    if (newPassword.length < PASSWORD_RULES.MIN_LENGTH) {
      Alert.alert(t.common.error, t.auth.passwordMin.replace('{n}', String(PASSWORD_RULES.MIN_LENGTH)));
      return;
    }
    if (PASSWORD_RULES.REQUIRE_UPPERCASE && !/[A-Z]/.test(newPassword)) {
      Alert.alert(t.common.error, t.auth.passwordUpper);
      return;
    }
    if (PASSWORD_RULES.REQUIRE_LOWERCASE && !/[a-z]/.test(newPassword)) {
      Alert.alert(t.common.error, t.auth.passwordLower);
      return;
    }
    if (PASSWORD_RULES.REQUIRE_NUMBER && !/[0-9]/.test(newPassword)) {
      Alert.alert(t.common.error, t.auth.passwordNumber);
      return;
    }

    // 验证密码确认
    if (newPassword !== confirmPassword) {
      Alert.alert(t.common.error, t.auth.passwordMismatch);
      return;
    }

    setIsLoading(true);
    try {
      await confirmResetPassword({ token, new_password: newPassword });
      Alert.alert(
        'Success',
        'Your password has been reset successfully',
        [
          {
            text: 'OK',
            onPress: () => navigation.navigate('EmailLogin'),
          },
        ]
      );
    } catch (error: any) {
      Alert.alert(t.common.error, error.message || t.auth.resetFailed);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Screen>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        {/* 标题 */}
        <View style={styles.header}>
          <Text style={styles.title}>Reset Password</Text>
          <Text style={styles.subtitle}>
            Enter your new password below
          </Text>
        </View>

        {/* 表单 */}
        <View style={styles.form}>
          {/* 新密码输入 */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>New Password</Text>
            <View style={styles.passwordContainer}>
              <TextField
                inputStyle={styles.passwordInput}
                placeholder="Enter new password"
                value={newPassword}
                onChangeText={setNewPassword}
                secureTextEntry={!showNewPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
                style={styles.eyeButton}
                onPress={() => setShowNewPassword(!showNewPassword)}
              >
                <Icon name={showNewPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>

            {/* 密码强度指示器 */}
            {newPassword.length > 0 && (
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
            <Text style={styles.inputLabel}>Confirm New Password</Text>
            <View style={styles.passwordContainer}>
              <TextField
                inputStyle={styles.passwordInput}
                placeholder="Re-enter new password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry={!showConfirmPassword}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!isLoading}
              />
              <TouchableOpacity
                style={styles.eyeButton}
                onPress={() => setShowConfirmPassword(!showConfirmPassword)}
              >
                <Icon name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.TEXT_SECONDARY} />
              </TouchableOpacity>
            </View>
          </View>

          {/* 重置按钮 */}
          <Button
            title="Reset Password"
            onPress={handleResetPassword}
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
    paddingVertical: 20,
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
});

export default ResetPasswordScreen;
