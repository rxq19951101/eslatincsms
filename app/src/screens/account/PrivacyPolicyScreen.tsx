import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { COLORS, LEGAL_URLS } from '../../constants/config';
import Icon from '../../components/ui/Icon';
import { useI18n } from '../../i18n';

const PrivacyPolicyScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();

  const openFullPolicy = () => {
    Linking.openURL(LEGAL_URLS.privacy);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
        </TouchableOpacity>
        <Text style={styles.title}>{t.account.privacy}</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.p}>{t.legal.privacyIntro}</Text>
        <Text style={styles.p}>{t.legal.contact}</Text>
        <TouchableOpacity style={styles.linkBtn} onPress={openFullPolicy}>
          <Text style={styles.linkText}>{t.legal.openInBrowser}</Text>
          <Icon name="open-outline" library="Ionicons" size={18} color={COLORS.PRIMARY} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 },
  title: { fontSize: 18, fontWeight: '600' },
  content: { padding: 16 },
  p: { fontSize: 14, color: COLORS.TEXT_SECONDARY, lineHeight: 22, marginBottom: 12 },
  linkBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 16,
    paddingVertical: 12,
  },
  linkText: { fontSize: 15, fontWeight: '600', color: COLORS.PRIMARY },
});

export default PrivacyPolicyScreen;
