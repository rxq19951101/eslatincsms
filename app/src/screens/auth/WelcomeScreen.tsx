/**
 * 欢迎页面
 * 应用入口页面，提供邮箱登录和社交登录选项
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';

type WelcomeScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Welcome'>;

const WelcomeScreen = () => {
  const navigation = useNavigation<WelcomeScreenNavigationProp>();

  const handleEmailSignIn = () => {
    navigation.navigate('EmailLogin');
  };

  const handleSignUp = () => {
    navigation.navigate('EmailRegister');
  };

  const handleGoogleSignIn = () => {
    // TODO: 实现Google登录
    console.log('Google Sign In');
  };

  const handleAppleSignIn = () => {
    // TODO: 实现Apple登录
    console.log('Apple Sign In');
  };

  const handleFacebookSignIn = () => {
    // TODO: 实现Facebook登录
    console.log('Facebook Sign In');
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />
      
      <View style={styles.content}>
        {/* Logo区域 */}
        <View style={styles.logoContainer}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoIcon}>⚡</Text>
          </View>
          <Text style={styles.appName}>EsLatin</Text>
          <Text style={styles.tagline}>Find & Charge Your EV</Text>
        </View>

        {/* 登录按钮组 */}
        <View style={styles.buttonsContainer}>
          {/* 邮箱登录按钮 */}
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleEmailSignIn}
            activeOpacity={0.8}
          >
            <Text style={styles.primaryButtonText}>Sign in with Email</Text>
          </TouchableOpacity>

          {/* 分隔线 */}
          <View style={styles.dividerContainer}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or continue with</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* 社交登录按钮组 */}
          <View style={styles.socialButtonsRow}>
            <TouchableOpacity
              style={[styles.socialButton, { marginRight: 8 }]}
              onPress={handleGoogleSignIn}
              activeOpacity={0.8}
            >
              <Text style={styles.socialButtonText}>G</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.socialButton, { marginHorizontal: 8 }]}
              onPress={handleAppleSignIn}
              activeOpacity={0.8}
            >
              <Text style={styles.socialButtonText}>🍎</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.socialButton, { marginLeft: 8 }]}
              onPress={handleFacebookSignIn}
              activeOpacity={0.8}
            >
              <Text style={styles.socialButtonText}>f</Text>
            </TouchableOpacity>
          </View>

          {/* 注册链接 */}
          <View style={styles.signupContainer}>
            <Text style={styles.signupText}>Don't have an account? </Text>
            <TouchableOpacity onPress={handleSignUp}>
              <Text style={styles.signupLink}>Sign Up</Text>
            </TouchableOpacity>
          </View>
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
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 40,
  },
  logoContainer: {
    alignItems: 'center',
    marginTop: 60,
  },
  logoCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: COLORS.PRIMARY,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  logoIcon: {
    fontSize: 50,
  },
  appName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  tagline: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
  },
  buttonsContainer: {
    width: '100%',
  },
  primaryButton: {
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
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  dividerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 24,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: COLORS.BORDER,
  },
  dividerText: {
    marginHorizontal: 16,
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  socialButtonsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginBottom: 32,
  },
  socialButton: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    justifyContent: 'center',
    alignItems: 'center',
  },
  socialButtonText: {
    fontSize: 24,
  },
  signupContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  signupText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  signupLink: {
    color: COLORS.PRIMARY,
    fontSize: 14,
    fontWeight: '600',
  },
});

export default WelcomeScreen;
