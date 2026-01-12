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
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';

type VerificationSuccessScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'VerificationSuccess'
>;

const VerificationSuccessScreen = () => {
  const navigation = useNavigation<VerificationSuccessScreenNavigationProp>();
  const scaleAnim = new Animated.Value(0);

  useEffect(() => {
    // 成功动画
    Animated.spring(scaleAnim, {
      toValue: 1,
      tension: 10,
      friction: 3,
      useNativeDriver: true,
    }).start();

    // 3秒后自动跳转
    const timer = setTimeout(() => {
      // TODO: navigation.navigate('MainTabs');
      navigation.navigate('Welcome');
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        {/* 成功图标动画 */}
        <Animated.View
          style={[
            styles.iconContainer,
            {
              transform: [{ scale: scaleAnim }],
            },
          ]}
        >
          <View style={styles.iconCircle}>
            <Text style={styles.checkmark}>✓</Text>
          </View>
          {/* 装饰点 */}
          <View style={[styles.dot, styles.dot1]} />
          <View style={[styles.dot, styles.dot2]} />
          <View style={[styles.dot, styles.dot3]} />
          <View style={[styles.dot, styles.dot4]} />
        </Animated.View>

        {/* 文本 */}
        <View style={styles.textContainer}>
          <Text style={styles.title}>Email Verified Successfully!</Text>
          <Text style={styles.subtitle}>Please wait...</Text>
          <Text style={styles.description}>
            You will be directed to the homepage
          </Text>
        </View>

        {/* 加载指示器 */}
        <View style={styles.loadingContainer}>
          <View style={[styles.loadingDot, { marginRight: 8 }]} />
          <View style={[styles.loadingDot, styles.loadingDot2, { marginRight: 8 }]} />
          <View style={[styles.loadingDot, styles.loadingDot3]} />
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
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  iconContainer: {
    position: 'relative',
    marginBottom: 40,
  },
  iconCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.SUCCESS,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkmark: {
    fontSize: 60,
    color: '#FFFFFF',
    fontWeight: 'bold',
  },
  dot: {
    position: 'absolute',
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: COLORS.SUCCESS,
  },
  dot1: {
    top: -10,
    right: 20,
  },
  dot2: {
    top: 20,
    right: -15,
  },
  dot3: {
    bottom: -10,
    left: 20,
  },
  dot4: {
    bottom: 20,
    left: -15,
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
  loadingContainer: {
    flexDirection: 'row',
  },
  loadingDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: COLORS.SUCCESS,
  },
  loadingDot2: {
    opacity: 0.7,
  },
  loadingDot3: {
    opacity: 0.4,
  },
});

export default VerificationSuccessScreen;
