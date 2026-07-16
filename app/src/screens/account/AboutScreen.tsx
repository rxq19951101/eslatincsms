import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import Constants from 'expo-constants';
import { COLORS } from '../../constants/config';
import Icon from '../../components/ui/Icon';
import { useI18n } from '../../i18n';

const AboutScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();
  const version =
    Constants.expoConfig?.version ||
    Constants.nativeAppVersion ||
    '1.0.0';

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
        </TouchableOpacity>
        <Text style={styles.title}>{t.about.title}</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.content}>
        <Text style={styles.appName}>{t.about.name}</Text>
        <Text style={styles.version}>{t.about.version.replace('{v}', version)}</Text>
        <Text style={styles.p}>{t.about.blurb}</Text>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 },
  title: { fontSize: 18, fontWeight: '600' },
  content: { padding: 24, alignItems: 'center' },
  appName: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
  version: { fontSize: 14, color: COLORS.TEXT_SECONDARY, marginBottom: 16 },
  p: { fontSize: 14, color: COLORS.TEXT_SECONDARY, textAlign: 'center' },
});

export default AboutScreen;
