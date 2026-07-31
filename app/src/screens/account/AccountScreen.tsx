/**
 * 账户页面
 */

import React, { useRef, useState } from 'react';
import {
  ScrollView,
  View,
  Text,
  StyleSheet,
  StatusBar,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES, PAYMENT_RAILS_ENABLED, LEGAL_URLS } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { logout } from '../../store/slices/authSlice';
import Button from '../../components/ui/Button';
import ListItem from '../../components/ui/ListItem';
import Card from '../../components/ui/Card';
import RootTabHeader from '../../components/ui/RootTabHeader';
import ConfirmationDialog from '../../components/ui/ConfirmationDialog';
import { useI18n } from '../../i18n';

type AccountScreenNavigationProp = StackNavigationProp<RootStackParamList>;

const AccountScreen = () => {
  const { t, locale } = useI18n();

  const navigation = useNavigation<AccountScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const [isLogoutDialogVisible, setIsLogoutDialogVisible] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const logoutInFlight = useRef(false);

  const handleLogout = () => {
    setIsLogoutDialogVisible(true);
  };

  const handleCancelLogout = () => {
    if (!isLoggingOut) {
      setIsLogoutDialogVisible(false);
    }
  };

  const handleConfirmLogout = async () => {
    if (logoutInFlight.current) return;

    logoutInFlight.current = true;
    setIsLoggingOut(true);
    try {
      await dispatch(logout());
      setIsLogoutDialogVisible(false);
      navigation.replace('Welcome');
    } finally {
      logoutInFlight.current = false;
      setIsLoggingOut(false);
    }
  };

  const currentLangLabel =
    locale === 'zh' ? t.account.languageZh : locale === 'en' ? t.account.languageEn : t.account.languageEs;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />

      <RootTabHeader title={t.account.title} testID="app-account-header" />

      <ScrollView
        testID="account-scroll-view"
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Card
          testID="personal-settings-open"
          accessibilityLabel={t.account.personal}
          onPress={() => navigation.navigate('PersonalInfo')}
          style={styles.profileCard}
        >
          <View style={styles.profileMain}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>
                {user?.full_name?.charAt(0).toUpperCase() || '?'}
              </Text>
            </View>
            <View style={styles.profileDetails}>
              <Text style={styles.userName}>{user?.full_name || t.account.userFallback}</Text>
              <Text style={styles.userEmail}>{user?.email || '—'}</Text>
            </View>
          </View>
          <View style={styles.profileEntry}>
            <Text style={styles.profileEntryText}>{t.account.personal}</Text>
            <Text style={styles.profileChevron}>›</Text>
          </View>
        </Card>

        <Text style={styles.sectionTitle}>{t.account.chargingAndPayments}</Text>
        <Card style={styles.menuSection}>
          <ListItem
            testID="app-history-open"
            accessibilityLabel={t.account.history}
            label={t.account.history}
            onPress={() => navigation.navigate('ChargingHistory')}
            index={0}
          />
          {PAYMENT_RAILS_ENABLED && (
            <ListItem
              label={t.account.payments}
              onPress={() => navigation.navigate('PaymentHub')}
              index={1}
            />
          )}
        </Card>

        <Text style={styles.sectionTitle}>{t.account.preferences}</Text>
        <Card style={styles.menuSection}>
          <ListItem
            testID="app-language-open"
            accessibilityLabel={t.account.language}
            label={`${t.account.language} · ${currentLangLabel}`}
            onPress={() => navigation.navigate('Language')}
            index={0}
          />
        </Card>

        <Text style={styles.sectionTitle}>{t.account.supportAndLegal}</Text>
        <Card style={styles.menuSection}>
          <ListItem
            label={t.account.help}
            onPress={() => navigation.navigate('HelpCenter')}
            index={0}
          />
          <ListItem
            label={t.account.privacy}
            onPress={() => navigation.navigate('PrivacyPolicy')}
            index={1}
          />
          <ListItem
            label={t.account.terms}
            onPress={() => Linking.openURL(LEGAL_URLS.terms)}
            index={2}
          />
          <ListItem
            label={t.account.about}
            onPress={() => navigation.navigate('About')}
            index={3}
            showArrow={false}
          />
        </Card>

        <View style={styles.logoutContainer}>
          <Button
            testID="logout-button"
            title={t.auth.logout}
            onPress={handleLogout}
            variant="outline"
            size="large"
            style={styles.logoutButton}
            textStyle={styles.logoutText}
          />
        </View>
      </ScrollView>

      <ConfirmationDialog
        visible={isLogoutDialogVisible}
        title={t.auth.logout}
        message={t.auth.logoutConfirm}
        cancelLabel={t.common.cancel}
        confirmLabel={t.auth.logout}
        onCancel={handleCancelLogout}
        onConfirm={handleConfirmLogout}
        loading={isLoggingOut}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  scrollContent: {
    paddingBottom: IOS_STYLES.SPACING.XL,
  },
  profileCard: {
    padding: IOS_STYLES.SPACING.LG,
    marginBottom: IOS_STYLES.SPACING.MD,
    marginHorizontal: IOS_STYLES.SPACING.MD,
  },
  profileMain: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: COLORS.PRIMARY_SOFT,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  avatarText: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.PRIMARY_DARK,
  },
  profileDetails: {
    flex: 1,
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
  profileEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.BORDER,
    marginTop: IOS_STYLES.SPACING.MD,
    paddingTop: IOS_STYLES.SPACING.MD,
  },
  profileEntryText: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.PRIMARY,
  },
  profileChevron: {
    fontSize: 24,
    lineHeight: 24,
    color: COLORS.TEXT_SECONDARY,
  },
  sectionTitle: {
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.SM,
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.TEXT_SECONDARY,
  },
  menuSection: {
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.LG,
    overflow: 'hidden',
  },
  logoutContainer: {
    marginHorizontal: IOS_STYLES.SPACING.MD,
  },
  logoutButton: {
    borderColor: COLORS.ERROR,
  },
  logoutText: {
    color: COLORS.ERROR,
  },
});

export default AccountScreen;
