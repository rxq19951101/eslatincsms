/**
 * 位置权限请求页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  Alert,
  Platform,
} from 'react-native';
import * as Location from 'expo-location';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';

type LocationPermissionScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'LocationPermission'
>;

const LocationPermissionScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<LocationPermissionScreenNavigationProp>();
  const [isRequesting, setIsRequesting] = useState(false);

  const requestLocationPermission = async (): Promise<'granted' | 'denied' | 'timeout'> => {
    const timeout = new Promise<'timeout'>((resolve) => {
      setTimeout(() => resolve('timeout'), 8000);
    });

    const permission = (async (): Promise<'granted' | 'denied'> => {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.geolocation) {
        return new Promise((resolve) => {
          navigator.geolocation.getCurrentPosition(
            () => resolve('granted'),
            () => resolve('denied'),
            { enableHighAccuracy: false, timeout: 7000, maximumAge: 60000 }
          );
        });
      }

      const { status } = await Location.requestForegroundPermissionsAsync();
      return status === 'granted' ? 'granted' : 'denied';
    })();

    return Promise.race([permission, timeout]);
  };

  const handleRequestPermission = async () => {
    setIsRequesting(true);
    try {
      const status = await requestLocationPermission();
      
      if (status === 'granted') {
        navigation.replace('MainTabs');
      } else if (status === 'timeout') {
        Alert.alert(t.location.title, t.location.timeout);
      } else {
        Alert.alert(t.location.title, t.location.required, [
          { text: t.common.cancel, style: 'cancel' },
          { text: t.common.ok },
        ]);
      }
    } catch (error) {
      console.error('Error requesting location permission:', error);
      Alert.alert(t.common.error, t.location.failed);
    } finally {
      setIsRequesting(false);
    }
  };

  const handleSkip = () => {
    navigation.replace('MainTabs');
  };

  return (
    <Screen edges={['top', 'bottom']}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        <View style={styles.textContainer}>
          <Text style={styles.title}>{t.location.title}</Text>
          <Text style={styles.subtitle}>{t.location.body}</Text>
          
          <View style={styles.featuresList}>
            <FeatureItem text={t.location.nearby} />
            <FeatureItem text={t.location.navigation} />
            <FeatureItem text={t.location.realtime} />
          </View>
        </View>

        <View style={styles.buttonsContainer}>
          <Button
            title={isRequesting ? t.common.loading : t.location.allow}
            onPress={handleRequestPermission}
            disabled={isRequesting}
            loading={isRequesting}
            size="large"
          />

          <Button title={t.location.skip} variant="text" onPress={handleSkip} disabled={isRequesting} />

          <Text style={styles.privacyText}>{t.legal.privacyIntro}</Text>
        </View>
      </View>
    </Screen>
  );
};

// 功能列表项组件
const FeatureItem = ({ text }: { text: string }) => (
  <View style={styles.featureItem}>
    <Text style={styles.featureText}>{text}</Text>
  </View>
);

const styles = StyleSheet.create({
  content: {
    flex: 1,
    paddingHorizontal: 24,
    paddingVertical: 40,
    justifyContent: 'space-between',
  },
  textContainer: {
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 16,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: 32,
    lineHeight: 24,
  },
  featuresList: {
    width: '100%',
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    paddingHorizontal: 16,
  },
  featureText: {
    fontSize: 16,
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
  },
  buttonsContainer: {
    width: '100%',
  },
  privacyText: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    lineHeight: 18,
  },
});

export default LocationPermissionScreen;
