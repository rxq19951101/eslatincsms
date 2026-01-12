/**
 * 个人信息（简化版）
 * - 先支持本地编辑 full_name/phone（仅用于展示）
 * - 后续可接后端 /me 更新接口
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, Alert, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList, User } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { setUser } from '../../store/slices/authSlice';
import { saveUserInfo } from '../../utils/tokenManager';

type Nav = StackNavigationProp<RootStackParamList, 'PersonalInfo'>;

const PersonalInfoScreen = () => {
  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((s) => s.auth);

  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setFullName(user?.full_name || '');
    setPhone(user?.phone || '');
  }, [user]);

  const onSave = async () => {
    if (!user) return;
    setSaving(true);
    try {
      const next: User = {
        ...user,
        full_name: fullName.trim(),
        phone: phone.trim() || undefined,
      };
      dispatch(setUser(next));
      await saveUserInfo(next);
      Alert.alert('已保存', Platform.OS === 'web' ? '本地保存成功（Web）' : '本地保存成功');
      navigation.goBack();
    } catch (e) {
      Alert.alert('保存失败', '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>个人信息</Text>
        <View style={styles.headerRight} />
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>邮箱</Text>
        <Text style={styles.readonly}>{user?.email || '—'}</Text>

        <Text style={[styles.label, { marginTop: 14 }]}>姓名</Text>
        <TextInput value={fullName} onChangeText={setFullName} placeholder="请输入姓名" style={styles.input} />

        <Text style={[styles.label, { marginTop: 14 }]}>手机号（可选）</Text>
        <TextInput value={phone} onChangeText={setPhone} placeholder="请输入手机号" style={styles.input} />
      </View>

      <View style={styles.bottomBar}>
        <TouchableOpacity style={[styles.btn, styles.primary, saving && styles.disabled]} disabled={saving} onPress={onSave}>
          <Text style={styles.primaryText}>{saving ? '保存中...' : '保存'}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: {
    height: 56,
    backgroundColor: '#FFFFFF',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.BORDER,
  },
  backBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 22, color: COLORS.TEXT_PRIMARY },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  headerRight: { width: 44 },
  card: {
    margin: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  label: { color: COLORS.TEXT_SECONDARY, fontSize: 12, marginBottom: 6 },
  readonly: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },
  input: {
    height: 44,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    paddingHorizontal: 12,
    backgroundColor: '#FFFFFF',
  },
  bottomBar: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  btn: { height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
  disabled: { opacity: 0.6 },
});

export default PersonalInfoScreen;

