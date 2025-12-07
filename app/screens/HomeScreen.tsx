/**
 * 本文件为 Home 页面：输入/选择桩号，跳转 Session。
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
} from 'react-native';

type HomeScreenProps = {
  navigation: any;
  user?: { username: string; idTag: string };
  onLogout?: () => void;
};

export default function HomeScreen({ navigation, user, onLogout }: HomeScreenProps) {
  const [chargerId, setChargerId] = useState('CP-0001');

  const handleGoToSession = () => {
    if (!chargerId.trim()) {
      Alert.alert('提示', '请输入充电桩ID');
      return;
    }
    navigation.navigate('Session', { chargerId: chargerId.trim() });
  };

  const handleGoToScan = () => {
    navigation.navigate('Scan');
  };

  return (
    <View style={styles.container}>
      {user && (
        <View style={styles.userInfo}>
          <Text style={styles.welcome}>欢迎, {user.username}!</Text>
          <Text style={styles.userId}>充电ID: {user.idTag}</Text>
          {onLogout && (
            <TouchableOpacity style={styles.logoutButton} onPress={onLogout}>
              <Text style={styles.logoutButtonText}>退出登录</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      <Text style={styles.title}>选择充电桩</Text>

      <View style={styles.inputContainer}>
        <Text style={styles.label}>充电桩ID</Text>
        <TextInput
          style={styles.input}
          placeholder="例如: CP-0001"
          value={chargerId}
          onChangeText={setChargerId}
        />
      </View>

      <TouchableOpacity style={styles.button} onPress={handleGoToSession}>
        <Text style={styles.buttonText}>开始充电</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.buttonSecondary} onPress={handleGoToScan}>
        <Text style={styles.buttonTextSecondary}>扫码充电</Text>
      </TouchableOpacity>

      <Text style={styles.hint}>提示：输入充电桩ID或点击扫码</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 28,
    fontWeight: '600',
    marginBottom: 32,
    marginTop: 16,
  },
  inputContainer: {
    marginBottom: 24,
  },
  label: {
    fontSize: 16,
    marginBottom: 8,
    color: '#333',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
  button: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  buttonSecondary: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#007AFF',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  buttonTextSecondary: {
    color: '#007AFF',
    fontSize: 18,
    fontWeight: '600',
  },
  hint: {
    color: '#666',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 16,
  },
  userInfo: {
    backgroundColor: '#f0f8ff',
    borderRadius: 8,
    padding: 16,
    marginBottom: 24,
  },
  welcome: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 4,
    color: '#007AFF',
  },
  userId: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  logoutButton: {
    backgroundColor: '#ff3b30',
    borderRadius: 8,
    padding: 8,
    alignItems: 'center',
  },
  logoutButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
});

