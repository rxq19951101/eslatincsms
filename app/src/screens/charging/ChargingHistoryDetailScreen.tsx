/**
 * 充电记录详情（PAY-MP-002 authoritative projection）
 *
 * The legacy P001 detail endpoint remains available to older consumers. The
 * App explicitly requests P002 so billing and payment facts are not inferred
 * from a session status or from client-side arithmetic.
 */

import React, { useEffect, useState } from 'react';
import { Alert, View, Text, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { localizeStatus } from '../../utils/localizeStatus';
import { formatDateTime } from '../../utils/localizedDisplay';
import { createSupportCase, getP002TransactionDetail, PayMp002Error } from '../../features/payMp002/adapter';
import Button from '../../components/ui/Button';
import type { P002PaymentStatus, P002TransactionProjection } from '../../features/payMp002/types';

type R = RouteProp<RootStackParamList, 'ChargingHistoryDetail'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingHistoryDetail'>;

const formatDecimalAmount = (amount: string, currency: string): string => {
  const match = amount.trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return `${amount} ${currency}`;
  const [, sign, integer, fraction = ''] = match;
  const groupedInteger = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const decimal = fraction ? `,${fraction}` : '';
  const symbol = currency === 'COP' ? '$' : '';
  return `${sign}${symbol}${groupedInteger}${decimal} ${currency}`.trim();
};

const paymentStatusLabel = (status: P002PaymentStatus | undefined, t: ReturnType<typeof useI18n>['t']) => {
  switch (status) {
    case 'paid': return t.history.billingPaid;
    case 'processing': return t.history.billingProcessing;
    case 'unpaid': return t.history.billingUnpaid;
    case 'refunded': return t.history.billingRefunded;
    case 'partially_refunded': return t.history.billingPartiallyRefunded;
    case 'disputed': return t.history.billingDisputed;
    default: return t.history.pendingSettlement;
  }
};

const dataQualityLabel = (
  quality: P002TransactionProjection['data_quality'],
  t: ReturnType<typeof useI18n>['t'],
) => {
  switch (quality) {
    case 'current': return t.history.dataQualityCurrent;
    case 'legacy': return t.history.dataQualityLegacy;
    default: return t.history.dataQualityUnknown;
  }
};

const ChargingHistoryDetailScreen = () => {
  const { t, locale } = useI18n();
  const navigation = useNavigation<Nav>();
  const route = useRoute<R>();
  const { id } = route.params;
  const [record, setRecord] = useState<P002TransactionProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<PayMp002Error | null>(null);
  const [supporting, setSupporting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void getP002TransactionDetail(id)
      .then((value) => {
        if (active) setRecord(value);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof PayMp002Error ? cause : null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [id]);

  const openSupport = async () => {
    if (!record || supporting || !record.allowed_actions?.includes('contact_support')) return;
    setSupporting(true);
    try {
      const supportCase = await createSupportCase({
        category: 'charging_issue',
        resource_type: record.invoice?.id ? 'invoice' : 'session',
        resource_id: record.invoice?.id || record.id,
      });
      Alert.alert(t.common.success, t.history.supportCreated, [
        { text: t.common.success, onPress: () => navigation.navigate('SupportCaseDetail', { caseId: supportCase.case_id }) },
      ]);
    } catch {
      Alert.alert(t.history.supportCreateFailed);
    } finally {
      setSupporting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader title={t.history.detail} onBack={() => navigation.goBack()} />
      {loading && !record ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.centerText}>{t.common.loading}</Text>
        </View>
      ) : !record ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{error ? t.history.loadFailed : t.history.notFound}</Text>
        </View>
      ) : (
        <ScrollView testID="app-history-detail" contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
          <View style={styles.card}>
            <Text style={styles.title}>{record.site_name || t.common.unknown}</Text>
            <Text style={styles.subTitle}>{record.site_address || '—'}</Text>
          </View>

          <View style={styles.card}>
            {record.invoice?.reference && <Row label={t.history.invoiceNumber} value={record.invoice.reference} />}
            {record.invoice_number && !record.invoice?.reference && (
              <Row label={t.history.invoiceNumber} value={record.invoice_number} />
            )}
            <Row
              label={t.history.finalAmount}
              value={record.invoice?.amount
                ? formatDecimalAmount(record.invoice.amount, record.invoice.currency)
                : record.total_amount
                  ? formatDecimalAmount(record.total_amount, record.currency || 'COP')
                  : t.history.pendingSettlement}
            />
            <Row label={t.history.billingStatus} value={paymentStatusLabel(record.payment_status, t)} />
            <Row label={t.history.dataQuality} value={dataQualityLabel(record.data_quality, t)} />
          </View>

          <View style={styles.card}>
            <Row label={t.history.status} value={localizeStatus(record.status, t)} />
            <Row label={t.history.startTime} value={formatDateTime(record.start_time, locale)} />
            <Row label={t.history.endTime} value={formatDateTime(record.end_time, locale)} />
            <Row label={t.history.charger} value={record.charge_point_label || t.common.unknown} />
            {(record.connector_label || typeof record.connector_number === 'number') && (
              <Row
                label={t.history.connector}
                value={record.connector_label || t.history.connectorFallback.replace('{number}', String(record.connector_number))}
              />
            )}
          </View>

          <View style={styles.card}>
            <Row label={t.history.energyKwh} value={record.energy_kwh || '—'} />
            <Row label={t.history.durationMin} value={record.duration_minutes || '—'} />
          </View>

          {record.payments && record.payments.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>{t.history.paymentFacts}</Text>
              {record.payments.map((payment) => (
                <Row key={payment.id} label={payment.method || t.history.billingStatus} value={payment.status} />
              ))}
            </View>
          )}

          {record.timeline && record.timeline.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>{t.history.timeline}</Text>
              {record.timeline.map((event) => (
                <View key={event.event_id} style={styles.timelineRow}>
                  <Text style={styles.timelineType}>{event.type}</Text>
                  <Text style={styles.timelineStatus}>{event.status} · {formatDateTime(event.occurred_at, locale)}</Text>
                </View>
              ))}
            </View>
          )}

          {record.allowed_actions?.includes('contact_support') && (
            <Button
              testID="app-history-contact-support"
              title={t.history.contactSupport}
              onPress={() => void openSupport()}
              variant="outline"
              loading={supporting}
              disabled={supporting}
            />
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
};

const Row = ({ label, value }: { label: string; value: string }) => (
  <View style={styles.row}>
    <Text style={styles.label}>{label}</Text>
    <Text style={styles.value}>{value}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerText: { marginTop: 10, color: COLORS.TEXT_SECONDARY },
  errorText: { color: COLORS.ERROR, fontWeight: '800' },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    marginBottom: 12,
  },
  title: { fontSize: 18, fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 8, color: COLORS.TEXT_SECONDARY },
  sectionTitle: { color: COLORS.TEXT_PRIMARY, fontWeight: '900', marginBottom: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 },
  label: { color: COLORS.TEXT_SECONDARY },
  value: { color: COLORS.TEXT_PRIMARY, fontWeight: '800', paddingLeft: 10, flexShrink: 1, textAlign: 'right' },
  timelineRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: COLORS.BORDER },
  timelineType: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },
  timelineStatus: { marginTop: 4, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
});

export default ChargingHistoryDetailScreen;
