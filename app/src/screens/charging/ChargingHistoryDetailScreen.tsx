/**
 * 充电记录详情（订单详情）
 */

import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargingRecordDetail } from '../../store/slices/transactionsSlice';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { localizeStatus } from '../../utils/localizeStatus';

type R = RouteProp<RootStackParamList, 'ChargingHistoryDetail'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingHistoryDetail'>;

function fmtTime(s?: string | null) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

const ChargingHistoryDetailScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const route = useRoute<R>();
  const { id } = route.params;

  const dispatch = useAppDispatch();
  const { selected, loadingDetail, error } = useAppSelector((st) => st.transactions);

  useEffect(() => {
    dispatch(fetchChargingRecordDetail(id));
  }, [dispatch, id]);

  const d = selected && selected.id === id ? selected : null;

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader title={t.history.detail} onBack={() => navigation.goBack()} />

      {loadingDetail && !d ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.centerText}>{t.common.loading}</Text>
        </View>
      ) : !d ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{error || t.history.notFound}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
          <View style={styles.card}>
            <Text style={styles.title}>{d.site_name || d.charge_point_id}</Text>
            <Text style={styles.subTitle}>{d.site_address || '—'}</Text>
          </View>

          <View style={styles.card}>
            <Row label={t.history.status} value={localizeStatus(d.status, t)} />
            <Row label={t.history.startTime} value={fmtTime(d.start_time)} />
            <Row label={t.history.endTime} value={fmtTime(d.end_time)} />
            <Row label={t.history.chargerId} value={d.charge_point_id} />
            <Row label="EVSE" value={String(d.evse_id)} />
            <Row label="TransactionId" value={String(d.transaction_id)} />
          </View>

          <View style={styles.card}>
            <Row label={t.history.energyKwh} value={typeof d.energy_kwh === 'number' ? d.energy_kwh.toFixed(2) : '—'} />
            <Row
              label={t.history.durationMin}
              value={typeof d.duration_minutes === 'number' ? d.duration_minutes.toFixed(1) : '—'}
            />
            {typeof d.meter_start === 'number' && <Row label="MeterStart(Wh)" value={String(d.meter_start)} />}
            {typeof d.meter_stop === 'number' && <Row label="MeterStop(Wh)" value={String(d.meter_stop)} />}
          </View>
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
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 },
  label: { color: COLORS.TEXT_SECONDARY },
  value: { color: COLORS.TEXT_PRIMARY, fontWeight: '800', paddingLeft: 10, flexShrink: 1, textAlign: 'right' },
});

export default ChargingHistoryDetailScreen;
