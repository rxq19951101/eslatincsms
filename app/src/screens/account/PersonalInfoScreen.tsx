/**
 * 个人信息（简化版）
 * - 先支持本地编辑 full_name/phone（仅用于展示）
 * - 后续可接后端 /me 更新接口
 */

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, View, Text, StyleSheet, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList, User } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { deleteAccount, setUser } from '../../store/slices/authSlice';
import { saveUserInfo } from '../../utils/tokenManager';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import ConfirmationDialog from '../../components/ui/ConfirmationDialog';
import { palette, spacing, typography } from '../../theme';

type Nav = StackNavigationProp<RootStackParamList, 'PersonalInfo'>;

const PersonalInfoScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const { user, isLoading } = useAppSelector((s) => s.auth);

  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);
  const [isDeleteDialogVisible, setIsDeleteDialogVisible] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteInFlight = useRef(false);

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

  const onDeleteAccount = () => {
    setDeleteError(null);
    setIsDeleteDialogVisible(true);
  };

  const onCancelDeleteAccount = () => {
    if (!isDeleting) {
      setIsDeleteDialogVisible(false);
    }
  };

  const onConfirmDeleteAccount = async () => {
    if (deleteInFlight.current) return;

    deleteInFlight.current = true;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await dispatch(deleteAccount()).unwrap();
      setIsDeleteDialogVisible(false);
      Alert.alert(t.auth.deleteAccountSuccess);
      navigation.replace('Welcome');
    } catch {
      setIsDeleteDialogVisible(false);
      setDeleteError(t.auth.deleteAccountError);
    } finally {
      deleteInFlight.current = false;
      setIsDeleting(false);
    }
  };

  return (
    <Screen>
      <ScreenHeader title={t.personal.title} onBack={() => navigation.goBack()} />

      <ScrollView
        testID="personal-settings-scroll-view"
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <Card style={styles.card}>
          <Text style={styles.label}>{t.personal.email}</Text>
          <Text style={styles.readonly}>{user?.email || '—'}</Text>

          <TextField label={t.personal.name} value={fullName} onChangeText={setFullName} placeholder={t.personal.namePlaceholder} />
          <TextField label={t.personal.phone} value={phone} onChangeText={setPhone} placeholder={t.personal.phonePlaceholder} />
        </Card>

        <Card testID="account-management-section" style={styles.dangerCard}>
          <Text style={styles.dangerTitle}>{t.personal.accountManagement}</Text>
          <Text style={styles.dangerDescription}>{t.personal.deleteAccountDescription}</Text>
          <Button
            testID="delete-account-button"
            title={t.auth.deleteAccount}
            onPress={onDeleteAccount}
            variant="outline"
            size="large"
            disabled={isLoading}
            loading={isLoading}
            style={styles.deleteButton}
            textStyle={styles.deleteText}
          />
          {deleteError && (
            <Text testID="delete-account-error" accessibilityRole="alert" style={styles.errorText}>
              {deleteError}
            </Text>
          )}
        </Card>
      </ScrollView>

      <View style={styles.bottomBar}>
        <Button title={saving ? t.personal.saving : t.common.save} disabled={saving} loading={saving} onPress={onSave} size="large" />
      </View>

      <ConfirmationDialog
        visible={isDeleteDialogVisible}
        title={t.auth.deleteAccountTitle}
        message={t.auth.deleteAccountMessage}
        cancelLabel={t.common.cancel}
        confirmLabel={t.auth.deleteAccountConfirm}
        onCancel={onCancelDeleteAccount}
        onConfirm={onConfirmDeleteAccount}
        loading={isDeleting}
      />
    </Screen>
  );
};

const styles = StyleSheet.create({
  scrollContent: {
    paddingBottom: spacing.lg,
  },
  card: {
    margin: spacing.md,
    padding: spacing.md,
    gap: spacing.md,
  },
  label: { color: palette.muted, fontSize: typography.caption, marginBottom: 6 },
  readonly: { color: palette.ink, fontWeight: typography.semibold },
  dangerCard: {
    marginHorizontal: spacing.md,
    padding: spacing.md,
    gap: spacing.md,
    borderColor: palette.danger,
  },
  dangerTitle: {
    color: palette.danger,
    fontSize: typography.label,
    fontWeight: typography.semibold,
  },
  dangerDescription: {
    color: palette.muted,
    fontSize: typography.body,
    lineHeight: 20,
  },
  deleteButton: {
    borderColor: palette.danger,
  },
  deleteText: {
    color: palette.danger,
  },
  errorText: {
    color: palette.danger,
    fontSize: typography.body,
  },
  bottomBar: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
});

export default PersonalInfoScreen;
