import React from 'react';
import { Text, StyleSheet, ScrollView, Linking } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { LEGAL_URLS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { palette, spacing, typography } from '../../theme';

const HelpCenterScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();
  return (
    <Screen>
      <ScreenHeader title={t.help.title} onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.h}>{t.help.howCharge}</Text>
        <Text style={styles.p}>{t.help.howChargeBody}</Text>
        <Text style={styles.h}>{t.help.howBalance}</Text>
        <Text style={styles.p}>{t.help.howBalanceBody}</Text>
        <Text style={styles.h}>{t.help.contact}</Text>
        <Text
          style={[styles.p, styles.link]}
          onPress={() => Linking.openURL(`mailto:${LEGAL_URLS.supportEmail}`)}
        >
          {LEGAL_URLS.supportEmail}
        </Text>
      </ScrollView>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  h: { fontSize: typography.label, fontWeight: typography.semibold, color: palette.ink, marginTop: spacing.lg, marginBottom: spacing.sm },
  p: { fontSize: typography.body, color: palette.muted, lineHeight: 22 },
  link: { color: palette.brand },
});

export default HelpCenterScreen;
