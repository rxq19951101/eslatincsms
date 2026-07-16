/**
 * 个人信息（简化版）
 * - 先支持本地编辑 full_name/phone（仅用于展示）
 * - 后续可接后端 /me 更新接口
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList, User } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { setUser } from '../../store/slices/authSlice';
import { saveUserInfo } from '../../utils/tokenManager';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import { palette, spacing, typography } from '../../theme';

type Nav = StackNavigationProp<RootStackParamList, 'PersonalInfo'>;

const PersonalInfoScreen = () => {
  const { t } = useI18n();

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
      Alert.alert(t.personal.saved, t.personal.savedBody);
      navigation.goBack();
    } catch (e) {
      Alert.alert(t.common.error, t.personal.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen>
      <ScreenHeader title={t.personal.title} onBack={() => navigation.goBack()} />

      <Card style={styles.card}>
        <Text style={styles.label}>{t.personal.email}</Text>
        <Text style={styles.readonly}>{user?.email || '—'}</Text>

        <TextField label={t.personal.name} value={fullName} onChangeText={setFullName} placeholder={t.personal.namePlaceholder} />
        <TextField label={t.personal.phone} value={phone} onChangeText={setPhone} placeholder={t.personal.phonePlaceholder} />
      </Card>

      <View style={styles.bottomBar}>
        <Button title={saving ? t.personal.saving : t.common.save} disabled={saving} loading={saving} onPress={onSave} size="large" />
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  card: {
    margin: spacing.md,
    padding: spacing.md,
    gap: spacing.md,
  },
  label: { color: palette.muted, fontSize: typography.caption, marginBottom: 6 },
  readonly: { color: palette.ink, fontWeight: typography.semibold },
  bottomBar: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
});

export default PersonalInfoScreen;
