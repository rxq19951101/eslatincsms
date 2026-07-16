/**
 * 位置权限请求页面
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  StatusBar,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';

type LocationPermissionScreenNavigationProp = StackNavigationProp<
  RootStackParamList,
  'LocationPermission'
>;

const LocationPermissionScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<LocationPermissionScreenNavigationProp>();
  const [isRequesting, setIsRequesting] = useState(false);

  const handleRequestPermission = async () => {
    setIsRequesting(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      
      if (status === 'granted') {
        navigation.replace('MainTabs', undefined);
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
    navigation.replace('MainTabs', undefined);
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.content}>
        <View style={styles.iconContainer}>
          <View style={styles.iconCircle}>
            <Text style={styles.icon}>📍</Text>
          </View>
          <View style={[styles.decorCircle, styles.decorCircle1]} />
          <View style={[styles.decorCircle, styles.decorCircle2]} />
        </View>

        <View style={styles.textContainer}>
          <Text style={styles.title}>{t.location.title}</Text>
          <Text style={styles.subtitle}>{t.location.body}</Text>
          
          <View style={styles.featuresList}>
            <FeatureItem icon="🔍" text="Encuentra estaciones cerca de ti" />
            <FeatureItem icon="🗺️" text="Navegación precisa" />
            <FeatureItem icon="⚡" text="Disponibilidad en tiempo real" />
          </View>
        </View>

        <View style={styles.buttonsContainer}>
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleRequestPermission}
            disabled={isRequesting}
            activeOpacity={0.8}
          >
            <Text style={styles.primaryButtonText}>
              {isRequesting ? t.common.loading : t.location.allow}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.skipButton}
            onPress={handleSkip}
            disabled={isRequesting}
          >
            <Text style={styles.skipButtonText}>{t.location.skip}</Text>
          </TouchableOpacity>

          <Text style={styles.privacyText}>{t.legal.privacyIntro}</Text>
        </View>
      </View>
    </SafeAreaView>
  );
};

// 功能列表项组件
const FeatureItem = ({ icon, text }: { icon: string; text: string }) => (
  <View style={styles.featureItem}>
    <Text style={styles.featureIcon}>{icon}</Text>
    <Text style={styles.featureText}>{text}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    paddingVertical: 40,
    justifyContent: 'space-between',
  },
  iconContainer: {
    alignItems: 'center',
    marginTop: 40,
    position: 'relative',
  },
  iconCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.PRIMARY + '20',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 2,
  },
  icon: {
    fontSize: 60,
  },
  decorCircle: {
    position: 'absolute',
    borderRadius: 1000,
    borderWidth: 2,
    borderColor: COLORS.PRIMARY + '20',
  },
  decorCircle1: {
    width: 160,
    height: 160,
    zIndex: 1,
  },
  decorCircle2: {
    width: 200,
    height: 200,
    zIndex: 0,
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
  featureIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  featureText: {
    fontSize: 16,
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
  },
  buttonsContainer: {
    width: '100%',
  },
  primaryButton: {
    backgroundColor: COLORS.PRIMARY,
    paddingVertical: 16,
    borderRadius: 25,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: COLORS.PRIMARY,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  skipButton: {
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
  },
  skipButtonText: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 14,
  },
  privacyText: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    lineHeight: 18,
  },
});

export default LocationPermissionScreen;
