import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { COLORS, LEGAL_URLS } from '../../constants/config';
import Icon from '../../components/ui/Icon';
import { useI18n } from '../../i18n';

const HelpCenterScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
        </TouchableOpacity>
        <Text style={styles.title}>{t.help.title}</Text>
        <View style={{ width: 24 }} />
      </View>
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
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 },
  title: { fontSize: 18, fontWeight: '600' },
  content: { padding: 16 },
  h: { fontSize: 16, fontWeight: '600', marginTop: 16, marginBottom: 8 },
  p: { fontSize: 14, color: COLORS.TEXT_SECONDARY, lineHeight: 22 },
  link: { color: COLORS.PRIMARY },
});

export default HelpCenterScreen;
