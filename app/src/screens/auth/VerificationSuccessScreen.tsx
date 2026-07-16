/**
 * 验证成功页面
 * 邮箱验证成功后显示，自动登录并跳转
 */

import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';

type VerificationSuccessScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'VerificationSuccess'
>;

const VerificationSuccessScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<VerificationSuccessScreenNavigationProp>();
  useEffect(() => {
    // 3秒后自动跳转
    const timer = setTimeout(() => {
      navigation.navigate('MainTabs');
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  return (
    <Screen>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        <Badge label={t.common.success} variant="success" />

        {/* 文本 */}
        <View style={styles.textContainer}>
          <Text style={styles.title}>{t.auth.verifiedTitle}</Text>
          <Text style={styles.subtitle}>{t.auth.verifiedWait}</Text>
          <Text style={styles.description}>
            You will be directed to the homepage
          </Text>
        </View>

        {/* 加载指示器 */}
        <LoadingSpinner size="small" />
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  textContainer: {
    alignItems: 'center',
    marginBottom: 40,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.SUCCESS,
    marginBottom: 12,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: 8,
    textAlign: 'center',
  },
  description: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
  },
});

export default VerificationSuccessScreen;
