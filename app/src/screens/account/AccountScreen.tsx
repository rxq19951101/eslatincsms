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
import { useI18n } from '../../i18n';

type AccountScreenNavigationProp = StackNavigationProp<RootStackParamList>;

const AccountScreen = () => {
  const { t, locale } = useI18n();

  const navigation = useNavigation<AccountScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { user, isLoading } = useAppSelector((state) => state.auth);

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
          testID="app-history-open"
          accessibilityLabel={t.account.history}
          label={t.account.history}
          onPress={() => navigation.navigate('ChargingHistory')}
          index={0}
        />
        <ListItem
          label={t.account.personal}
          onPress={() => navigation.navigate('PersonalInfo')}
          index={1}
        />
        {PAYMENT_RAILS_ENABLED && (
          <ListItem
            label={t.account.payments}
            onPress={() => navigation.navigate('PaymentHub')}
            index={2}
          />
        )}
        <ListItem
          testID="app-language-open"
          accessibilityLabel={t.account.language}
          label={`${t.account.language} · ${currentLangLabel}`}
          onPress={() => navigation.navigate('Language')}
          index={3}
        />
        <ListItem
          label={t.account.help}
          onPress={() => navigation.navigate('HelpCenter')}
          index={4}
        />
        <ListItem
          label={t.account.privacy}
          onPress={() => navigation.navigate('PrivacyPolicy')}
          index={5}
        />
        <ListItem
          label={t.account.terms}
          onPress={() => Linking.openURL(LEGAL_URLS.terms)}
          index={6}
        />
        <ListItem
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
    paddingTop: 20,
    paddingBottom: 18,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: COLORS.TEXT_PRIMARY,
  },
  profileCard: {
    alignItems: 'flex-start',
    padding: IOS_STYLES.SPACING.LG,
    marginBottom: IOS_STYLES.SPACING.MD,
    marginHorizontal: IOS_STYLES.SPACING.MD,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: COLORS.PRIMARY_SOFT,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  avatarText: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.PRIMARY_DARK,
  },
  userName: {
    fontSize: 20,
    fontWeight: '600',
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
