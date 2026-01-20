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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { logout } from '../../store/slices/authSlice';
import Icon from '../../components/ui/Icon';
import Button from '../../components/ui/Button';
import ListItem from '../../components/ui/ListItem';
import Card from '../../components/ui/Card';

type AccountScreenNavigationProp = StackNavigationProp<RootStackParamList>;

const AccountScreen = () => {
  const navigation = useNavigation<AccountScreenNavigationProp>();
  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await dispatch(logout());
            navigation.replace('Welcome');
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Account</Text>
      </View>

      {/* User Profile */}
      <Card style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {user?.full_name?.charAt(0).toUpperCase() || '?'}
          </Text>
        </View>
        <Text style={styles.userName}>{user?.full_name || 'User'}</Text>
        <Text style={styles.userEmail}>{user?.email || 'No email'}</Text>
      </Card>

      {/* Menu Items */}
      <Card style={styles.menuSection}>
        <ListItem
          icon={{ name: 'document-text', library: 'Ionicons' }}
          label="Charging History"
          onPress={() => navigation.navigate('ChargingHistory')}
          index={0}
        />
        <ListItem
          icon={{ name: 'person', library: 'Ionicons' }}
          label="Personal Information"
          onPress={() => navigation.navigate('PersonalInfo')}
          index={1}
        />
        <ListItem
          icon={{ name: 'card', library: 'Ionicons' }}
          label="Payment Methods"
          onPress={() => navigation.navigate('PaymentMethods')}
          index={2}
        />
        <ListItem
          icon={{ name: 'notifications', library: 'Ionicons' }}
          label="Notifications"
          onPress={() => {}}
          index={3}
        />
        <ListItem
          icon={{ name: 'globe', library: 'Ionicons' }}
          label="Language"
          onPress={() => navigation.navigate('Language')}
          index={4}
        />
        <ListItem
          icon={{ name: 'help-circle', library: 'Ionicons' }}
          label="Help & Support"
          onPress={() => navigation.navigate('HelpCenter')}
          index={5}
        />
        <ListItem
          icon={{ name: 'document', library: 'Ionicons' }}
          label="Privacy Policy"
          onPress={() => navigation.navigate('PrivacyPolicy')}
          index={6}
        />
        <ListItem
          icon={{ name: 'information-circle', library: 'Ionicons' }}
          label="About"
          onPress={() => navigation.navigate('About')}
          index={7}
          showArrow={false}
        />
      </Card>

      {/* Logout Button */}
      <View style={styles.logoutContainer}>
        <Button
          title="Logout"
          onPress={handleLogout}
          variant="outline"
          size="large"
          style={styles.logoutButton}
          textStyle={styles.logoutText}
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
  },
  logoutButton: {
    borderColor: COLORS.ERROR,
  },
  logoutText: {
    color: COLORS.ERROR,
  },
});

export default AccountScreen;
