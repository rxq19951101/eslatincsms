/**
 * 账户页面
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  Alert,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES, PAYMENT_RAILS_ENABLED, LEGAL_URLS } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { logout, deleteAccount } from '../../store/slices/authSlice';
import Button from '../../components/ui/Button';
import ListItem from '../../components/ui/ListItem';
import Card from '../../components/ui/Card';
import { useI18n, type AppLocale } from '../../i18n';

type AccountScreenNavigationProp = StackNavigationProp<RootStackParamList>;

const LANG_OPTIONS: { code: AppLocale; labelKey: 'languageEs' | 'languageZh' | 'languageEn' }[] = [
  { code: 'es', labelKey: 'languageEs' },
  { code: 'zh', labelKey: 'languageZh' },
  { code: 'en', labelKey: 'languageEn' },
];

const AccountScreen = () => {
  const { t, locale, setLocale } = useI18n();

  const navigation = useNavigation<AccountScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { user, isLoading } = useAppSelector((state) => state.auth);

  const handleLanguage = () => {
    Alert.alert(
      t.account.language,
      undefined,
      [
        ...LANG_OPTIONS.map((opt) => ({
          text: `${locale === opt.code ? '✓ ' : ''}${t.account[opt.labelKey]}`,
          onPress: () => setLocale(opt.code),
        })),
        { text: t.common.cancel, style: 'cancel' as const },
      ]
    );
  };

  const handleLogout = () => {
    Alert.alert(t.auth.logout, t.auth.logoutConfirm, [
      { text: t.common.cancel, style: 'cancel' },
      {
        text: t.auth.logout,
        style: 'destructive',
        onPress: async () => {
          await dispatch(logout());
          navigation.replace('Welcome');
        },
      },
    ]);
  };

  const handleDeleteAccount = () => {
    Alert.alert(t.auth.deleteAccountTitle, t.auth.deleteAccountMessage, [
      { text: t.common.cancel, style: 'cancel' },
      {
        text: t.auth.deleteAccountConfirm,
        style: 'destructive',
        onPress: async () => {
          try {
            await dispatch(deleteAccount()).unwrap();
            Alert.alert(t.auth.deleteAccountSuccess);
            navigation.replace('Welcome');
          } catch (e: any) {
            Alert.alert(t.auth.deleteAccountError, e?.message || String(e));
          }
        },
      },
    ]);
  };

  const currentLangLabel =
    locale === 'zh' ? t.account.languageZh : locale === 'en' ? t.account.languageEn : t.account.languageEs;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.header}>
        <Text style={styles.headerTitle}>{t.account.title}</Text>
      </View>

      <Card style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {user?.full_name?.charAt(0).toUpperCase() || '?'}
          </Text>
        </View>
        <Text style={styles.userName}>{user?.full_name || t.account.userFallback}</Text>
        <Text style={styles.userEmail}>{user?.email || '—'}</Text>
      </Card>

      <Card style={styles.menuSection}>
        <ListItem
          icon={{ name: 'document-text', library: 'Ionicons' }}
          label={t.account.history}
          onPress={() => navigation.navigate('ChargingHistory')}
          index={0}
        />
        <ListItem
          icon={{ name: 'person', library: 'Ionicons' }}
          label={t.account.personal}
          onPress={() => navigation.navigate('PersonalInfo')}
          index={1}
        />
        {PAYMENT_RAILS_ENABLED && (
          <ListItem
            icon={{ name: 'card', library: 'Ionicons' }}
            label={t.account.payments}
            onPress={() => navigation.navigate('PaymentHub')}
            index={2}
          />
        )}
        <ListItem
          icon={{ name: 'language', library: 'Ionicons' }}
          label={`${t.account.language} · ${currentLangLabel}`}
          onPress={handleLanguage}
          index={3}
        />
        <ListItem
          icon={{ name: 'help-circle', library: 'Ionicons' }}
          label={t.account.help}
          onPress={() => navigation.navigate('HelpCenter')}
          index={4}
        />
        <ListItem
          icon={{ name: 'document', library: 'Ionicons' }}
          label={t.account.privacy}
          onPress={() => navigation.navigate('PrivacyPolicy')}
          index={5}
        />
        <ListItem
          icon={{ name: 'document-text', library: 'Ionicons' }}
          label={t.account.terms}
          onPress={() => Linking.openURL(LEGAL_URLS.terms)}
          index={6}
        />
        <ListItem
          icon={{ name: 'information-circle', library: 'Ionicons' }}
          label={t.account.about}
          onPress={() => navigation.navigate('About')}
          index={7}
          showArrow={false}
        />
      </Card>

      <View style={styles.logoutContainer}>
        <Button
          title={t.auth.logout}
          onPress={handleLogout}
          variant="outline"
          size="large"
          style={styles.logoutButton}
          textStyle={styles.logoutText}
        />
        <Button
          title={t.auth.deleteAccount}
          onPress={handleDeleteAccount}
          variant="outline"
          size="large"
          disabled={isLoading}
          loading={isLoading}
          style={styles.deleteButton}
          textStyle={styles.deleteText}
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
  },
  profileCard: {
    alignItems: 'center',
    paddingVertical: IOS_STYLES.SPACING.LG,
    marginBottom: IOS_STYLES.SPACING.MD,
    marginHorizontal: IOS_STYLES.SPACING.MD,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: COLORS.PRIMARY,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  userName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 4,
  },
  userEmail: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  menuSection: {
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.LG,
    overflow: 'hidden',
  },
  logoutContainer: {
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.XL,
    gap: 12,
  },
  logoutButton: {
    borderColor: COLORS.ERROR,
  },
  logoutText: {
    color: COLORS.ERROR,
  },
  deleteButton: {
    borderColor: COLORS.TEXT_SECONDARY,
  },
  deleteText: {
    color: COLORS.TEXT_SECONDARY,
  },
});

export default AccountScreen;
