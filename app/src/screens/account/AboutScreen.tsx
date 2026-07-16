import React from 'react';
import { Text, StyleSheet } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Constants from 'expo-constants';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { palette, spacing, typography } from '../../theme';

const AboutScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();
  const version =
    Constants.expoConfig?.version ||
    Constants.nativeAppVersion ||
    '1.0.0';

  return (
    <Screen>
      <ScreenHeader title={t.about.title} onBack={() => navigation.goBack()} />
      <Text style={styles.content}>
        <Text style={styles.appName}>{t.about.name}</Text>
        {'\n'}
        <Text style={styles.version}>{t.about.version.replace('{v}', version)}</Text>
        {'\n\n'}
        <Text style={styles.p}>{t.about.blurb}</Text>
      </Text>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: { padding: spacing.lg, textAlign: 'center', color: palette.muted },
  appName: { fontSize: typography.title, fontWeight: typography.bold, color: palette.ink },
  version: { fontSize: typography.body, color: palette.muted },
  p: { fontSize: typography.body, color: palette.muted, lineHeight: 22 },
});

export default AboutScreen;
