import React from 'react';
import { Text, StyleSheet, ScrollView, Linking } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { LEGAL_URLS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Button from '../../components/ui/Button';
import { palette, spacing, typography } from '../../theme';

const PrivacyPolicyScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();

  const openFullPolicy = () => {
    Linking.openURL(LEGAL_URLS.privacy);
  };

  return (
    <Screen>
      <ScreenHeader title={t.account.privacy} onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.p}>{t.legal.privacyIntro}</Text>
        <Text style={styles.p}>{t.legal.contact}</Text>
        <Button title={t.legal.openInBrowser} variant="outline" onPress={openFullPolicy} style={styles.linkBtn} />
      </ScrollView>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  p: { fontSize: typography.body, color: palette.muted, lineHeight: 22, marginBottom: 12 },
  linkBtn: { marginTop: spacing.md },
});

export default PrivacyPolicyScreen;
