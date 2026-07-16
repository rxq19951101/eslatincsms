/**
 * Pantalla de carga finalizada (solo flujo QR)
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { formatMoneyCOP } from '../../utils/formatMoney';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { settleCharging, SettleResult } from '../../api/charging';
import { fetchWalletBalance, fetchWalletTransactions } from '../../store/slices/walletSlice';
import { useI18n } from '../../i18n';

type R = RouteProp<RootStackParamList, 'ChargingComplete'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingComplete'>;

const ChargingCompleteScreen = () => {
  const { t } = useI18n();

  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();

  const dispatch = useAppDispatch();
  const { lastStoppedSession, lastRemoteResult } = useAppSelector((s) => s.charging);
  const chargePointId = route.params.chargePointId || lastStoppedSession?.charge_point_id || '—';

  const [settling, setSettling] = useState(false);
  const [settleResult, setSettleResult] = useState<SettleResult | null>(null);
  const [settleError, setSettleError] = useState<string | null>(null);

  useEffect(() => {
    if (!lastStoppedSession) return;
    let cancelled = false;
    (async () => {
      try {
        setSettling(true);
        setSettleError(null);
        const res = await settleCharging(lastStoppedSession.id);
        if (cancelled) return;
        setSettleResult(res);
        dispatch(fetchWalletBalance());
        dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
      } catch (e: any) {
        if (cancelled) return;
        const msg =
          e?.response?.data?.detail ||
          e?.response?.data?.message ||
          e?.message ||
          t.charging.settleFail;
        setSettleError(msg);
      } finally {
        if (!cancelled) setSettling(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dispatch, lastStoppedSession]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.icon}>✅</Text>
        <Text style={styles.title}>{t.charging.completeTitle}</Text>
        <Text style={styles.subTitle}>{t.charging.charger.replace('{id}', String(chargePointId))}</Text>

        {lastStoppedSession && (
          <View style={styles.block}>
            <Text style={styles.kv}>
              {t.charging.sessionId.replace('{id}', String(lastStoppedSession.id))}
            </Text>
            <Text style={styles.kv}>TransactionId: {lastStoppedSession.transaction_id}</Text>
          </View>
        )}

        {lastRemoteResult && (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              {lastRemoteResult.success ? t.charging.stopOk : t.charging.stopFail}
              {lastRemoteResult.message}
            </Text>
          </View>
        )}

        <View style={styles.block}>
          <Text style={styles.kvTitle}>{t.charging.settle}</Text>
          {settling && (
            <View style={styles.settleRow}>
              <ActivityIndicator size="small" color={COLORS.PRIMARY} />
              <Text style={styles.settleText}>{t.charging.settling}</Text>
            </View>
          )}
          {!!settleError && <Text style={styles.errorText}>{settleError}</Text>}
          {!!settleResult && (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.kv}>
                {settleResult.already_settled ? t.charging.alreadySettled : t.charging.chargedNow}:{' '}
                {formatMoneyCOP(settleResult.charged_amount)}
              </Text>
              <Text style={styles.kv}>
                {t.charging.balance}: {formatMoneyCOP(settleResult.balance)} ({settleResult.currency})
              </Text>
              {typeof settleResult.energy_kwh === 'number' && (
                <Text style={styles.kv}>
                  {t.charging.energy}: {settleResult.energy_kwh.toFixed(3)} kWh
                </Text>
              )}
              {typeof settleResult.price_per_kwh === 'number' && (
                <Text style={styles.kv}>
                  {t.charging.pricePerKwh}: ${settleResult.price_per_kwh.toFixed(2)}/kWh
                </Text>
              )}
            </View>
          )}
        </View>

        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.secondary]}
            onPress={() => navigation.navigate('MainTabs')}
          >
            <Text style={styles.secondaryText}>{t.charging.home}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.primary]}
            onPress={() => navigation.navigate('MainTabs')}
          >
            <Text style={styles.primaryText}>{t.charging.scanAgain}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND, justifyContent: 'center', padding: 20 },
  card: { backgroundColor: '#fff', borderRadius: 16, padding: 20 },
  icon: { fontSize: 40, textAlign: 'center', marginBottom: 8 },
  title: { fontSize: 22, fontWeight: '700', textAlign: 'center', marginBottom: 8 },
  subTitle: { fontSize: 14, color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },
  block: { marginTop: 12 },
  kvTitle: { fontSize: 16, fontWeight: '600', marginBottom: 4 },
  kv: { fontSize: 14, color: COLORS.TEXT_PRIMARY, marginTop: 4 },
  notice: { marginTop: 12, padding: 10, backgroundColor: '#F3F4F6', borderRadius: 8 },
  noticeText: { fontSize: 13, color: COLORS.TEXT_SECONDARY },
  settleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  settleText: { marginLeft: 8, color: COLORS.TEXT_SECONDARY },
  errorText: { color: COLORS.ERROR, marginTop: 8 },
  row: { flexDirection: 'row', marginTop: 24, gap: 12 },
  btn: { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY },
  secondary: { backgroundColor: '#E5E7EB' },
  primaryText: { color: '#fff', fontWeight: '600' },
  secondaryText: { color: COLORS.TEXT_PRIMARY, fontWeight: '600' },
});

export default ChargingCompleteScreen;
