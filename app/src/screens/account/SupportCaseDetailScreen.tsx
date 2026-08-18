import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { formatDateTime } from '../../utils/localizedDisplay';
import { getSupportCase, PayMp002Error } from '../../features/payMp002/adapter';
import type { SupportCaseProjection } from '../../features/payMp002/types';
import Button from '../../components/ui/Button';

type R = RouteProp<RootStackParamList, 'SupportCaseDetail'>;
type Nav = StackNavigationProp<RootStackParamList, 'SupportCaseDetail'>;

const SupportCaseDetailScreen = () => {
  const { t, locale } = useI18n();
  const navigation = useNavigation<Nav>();
  const { caseId } = useRoute<R>().params;
  const [item, setItem] = useState<SupportCaseProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<PayMp002Error | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    let active = true;
    void getSupportCase(caseId)
      .then((value) => { if (active) setItem(value); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof PayMp002Error ? cause : null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [caseId]);

  useEffect(() => {
    const cleanup = load();
    return cleanup;
  }, [load]);

  return (
    <View style={styles.container}>
      <ScreenHeader title={t.history.supportCases} onBack={() => navigation.goBack()} />
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.PRIMARY} /><Text style={styles.sub}>{t.common.loading}</Text></View>
      ) : !item ? (
        <View style={styles.center}>
          <Text style={styles.error}>{error ? t.history.loadFailed : t.history.notFound}</Text>
          {error && <Button title={t.common.retry} onPress={load} variant="outline" size="small" style={styles.retry} />}
        </View>
      ) : (
        <ScrollView testID="app-support-case-detail" contentContainerStyle={styles.content}>
          <View style={styles.card}>
            <Text style={styles.title}>{item.reference}</Text>
            <Row label={t.history.supportStatus} value={item.status} />
            <Row label={t.history.supportSla} value={formatDateTime(item.sla_target_at, locale)} />
            {item.linked_refund_case?.reference && <Row label={t.history.linkedRefund} value={item.linked_refund_case.reference} />}
          </View>
          <View style={styles.card}>
            <Text style={styles.section}>{t.history.timeline}</Text>
            {item.timeline.length === 0 ? <Text style={styles.sub}>{t.history.supportEmpty}</Text> : item.timeline.map((event) => (
              <View key={event.event_id} style={styles.event}>
                <Text style={styles.eventTitle}>{event.event_type} · {event.status}</Text>
                <Text style={styles.sub}>{formatDateTime(event.occurred_at, locale)}</Text>
              </View>
            ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
};

const Row = ({ label, value }: { label: string; value: string }) => (
  <View style={styles.row}><Text style={styles.sub}>{label}</Text><Text style={styles.value}>{value}</Text></View>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { padding: 16, paddingBottom: 24 },
  card: { backgroundColor: '#FFF', borderWidth: 1, borderColor: COLORS.BORDER, borderRadius: 14, padding: 16, marginBottom: 12 },
  title: { color: COLORS.TEXT_PRIMARY, fontSize: 18, fontWeight: '900', marginBottom: 8 },
  section: { color: COLORS.TEXT_PRIMARY, fontWeight: '900', marginBottom: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 },
  value: { color: COLORS.TEXT_PRIMARY, fontWeight: '800', paddingLeft: 12, textAlign: 'right' },
  sub: { color: COLORS.TEXT_SECONDARY },
  error: { color: COLORS.ERROR, fontWeight: '800' },
  event: { borderTopWidth: 1, borderTopColor: COLORS.BORDER, paddingVertical: 10 },
  eventTitle: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },
  retry: { marginTop: 12 },
});

export default SupportCaseDetailScreen;
