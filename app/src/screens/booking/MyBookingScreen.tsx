/**
 * Pantalla de reservas
 */
import React from 'react';
import { View, Text, StyleSheet, StatusBar } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Icon from '../../components/ui/Icon';

const MyBookingScreen = () => {
  const { t } = useI18n();
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{t.booking.title}</Text>
      </View>
      <View style={styles.emptyState}>
        <Icon name="calendar-outline" size={56} color={COLORS.TEXT_TERTIARY} style={styles.emptyIcon} />
        <Text style={styles.emptyTitle}>{t.booking.emptyTitle}</Text>
        <Text style={styles.emptySubtitle}>{t.booking.emptySubtitle}</Text>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: { paddingHorizontal: 20, paddingVertical: 16 },
  headerTitle: { fontSize: 24, fontWeight: 'bold', color: COLORS.TEXT_PRIMARY },
  emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 40 },
  emptyIcon: { marginBottom: 16 },
  emptyTitle: { fontSize: 18, fontWeight: '600', color: COLORS.TEXT_PRIMARY, marginBottom: 8 },
  emptySubtitle: { fontSize: 14, color: COLORS.TEXT_SECONDARY, textAlign: 'center' },
});

export default MyBookingScreen;
