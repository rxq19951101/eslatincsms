/**
 * 本文件为注册页面：用户注册。
 * 仅用于本地测试与演示。
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

type RegisterScreenProps = {
  navigation: any;
  onLogin: (user: { username: string; idTag: string }) => void;
};

export default function RegisterScreen({ navigation, onLogin }: RegisterScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);

  const generateIdTag = (username: string) => {
    // 生成一个简单的 ID Tag，格式：USER_用户名_随机数
    const random = Math.floor(Math.random() * 10000);
    return `USER_${username.toUpperCase()}_${random}`;
  };

  const handleRegister = async () => {
    if (!username.trim()) {
      Alert.alert('提示', '请输入用户名');
      return;
    }

    if (!password.trim() || password.length < 6) {
      Alert.alert('提示', '密码至少需要6位');
      return;
    }

    if (password !== confirmPassword) {
      Alert.alert('提示', '两次密码输入不一致');
      return;
    }

    try {
      setLoading(true);

      // 检查用户是否已存在
      const existingUser = await AsyncStorage.getItem(`user_${username}`);
      if (existingUser) {
        Alert.alert('错误', '用户名已存在');
        return;
      }

      // 生成 ID Tag
      const idTag = generateIdTag(username);

      // 保存用户信息
      const userData = {
        username,
        password,
        phone: phone.trim(),
        idTag,
        createdAt: new Date().toISOString(),
      };

      await AsyncStorage.setItem(`user_${username}`, JSON.stringify(userData));

      // 自动登录
      await AsyncStorage.setItem('current_user', JSON.stringify({
        username,
        idTag,
      }));

      Alert.alert('成功', `注册成功！\n您的充电ID: ${idTag}`, [
        { text: '确定', onPress: () => onLogin({ username, idTag }) }
      ]);
    } catch (error) {
      Alert.alert('错误', '注册失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.container}
    >
      <View style={styles.content}>
        <Text style={styles.title}>注册账户</Text>
        <Text style={styles.subtitle}>创建您的充电账户</Text>

        <View style={styles.inputContainer}>
          <Text style={styles.label}>用户名</Text>
          <TextInput
            style={styles.input}
            placeholder="请输入用户名"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <View style={styles.inputContainer}>
          <Text style={styles.label}>手机号（可选）</Text>
          <TextInput
            style={styles.input}
            placeholder="请输入手机号"
            value={phone}
            onChangeText={setPhone}
            keyboardType="phone-pad"
          />
        </View>

        <View style={styles.inputContainer}>
          <Text style={styles.label}>密码</Text>
          <TextInput
            style={styles.input}
            placeholder="至少6位密码"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <View style={styles.inputContainer}>
          <Text style={styles.label}>确认密码</Text>
          <TextInput
            style={styles.input}
            placeholder="再次输入密码"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleRegister}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>注册</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.buttonSecondary}
          onPress={() => navigation.goBack()}
        >
          <Text style={styles.buttonTextSecondary}>已有账户？登录</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  content: {
    flex: 1,
    padding: 24,
    justifyContent: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
    color: '#007AFF',
  },
  subtitle: {
    fontSize: 16,
    marginBottom: 32,
    textAlign: 'center',
    color: '#666',
  },
  inputContainer: {
    marginBottom: 20,
  },
  label: {
    fontSize: 16,
    marginBottom: 8,
    color: '#333',
    fontWeight: '600',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 16,
    fontSize: 16,
    backgroundColor: '#f9f9f9',
  },
  button: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginBottom: 16,
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonSecondary: {
    backgroundColor: 'transparent',
    padding: 16,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  buttonTextSecondary: {
    color: '#007AFF',
    fontSize: 16,
    fontWeight: '500',
  },
});

