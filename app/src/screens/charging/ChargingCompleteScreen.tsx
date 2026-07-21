/**
 * Pantalla de carga finalizada (solo flujo QR)
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
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
import Screen from '../../components/ui/Screen';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import { radius, spacing, typography } from '../../theme';
import { publicChargerIdentity } from '../../utils/localizedDisplay';

type R = RouteProp<RootStackParamList, 'ChargingComplete'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingComplete'>;

const ChargingCompleteScreen = () => {
  const { t } = useI18n();

  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();

  const dispatch = useAppDispatch();
  const { lastStoppedSession, lastRemoteResult } = useAppSelector((s) => s.charging);
  const ocppIdentity = route.params.ocppIdentity || publicChargerIdentity(lastStoppedSession);

  const [settling, setSettling] = useState(false);
  const [settleResult, setSettleResult] = useState<SettleResult | null>(null);
  const [settleError, setSettleError] = useState(false);

  useEffect(() => {
    if (!lastStoppedSession) return;
    let cancelled = false;
    (async () => {
      try {
        setSettling(true);
        setSettleError(false);
        const res = await settleCharging(lastStoppedSession.id);
        if (cancelled) return;
        setSettleResult(res);
        dispatch(fetchWalletBalance());
        dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
      } catch {
        if (cancelled) return;
        setSettleError(true);
      } finally {
        if (!cancelled) setSettling(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dispatch, lastStoppedSession]);

  return (
    <Screen testID="app-charging-complete" accessibilityLabel={t.charging.completeTitle} edges={['top', 'bottom']} contentStyle={styles.container}>
      <Card style={styles.card}>
        <Badge label={t.common.success} variant="success" style={styles.statusBadge} />
        <Text style={styles.title}>{t.charging.completeTitle}</Text>
        <Text style={styles.subTitle}>{t.charging.charger.replace('{id}', ocppIdentity)}</Text>

        {lastRemoteResult && (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              {lastRemoteResult.success ? t.charging.stopped : t.charging.stopFailedGeneric}
            </Text>
          </View>
        )}

        <View style={styles.block}>
          <Text style={styles.kvTitle}>{t.charging.settle}</Text>
          {settling && (
            <View testID="app-charging-settling" style={styles.settleRow}>
              <ActivityIndicator size="small" color={COLORS.PRIMARY} />
              <Text style={styles.settleText}>{t.charging.settling}</Text>
            </View>
          )}
          {settleError && <Text testID="app-charging-settle-error" accessibilityRole="alert" style={styles.errorText}>{t.charging.settleFail}</Text>}
          {!!settleResult && (
            <View testID="app-charging-settled" style={{ marginTop: 8 }}>
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
          <Button title={t.charging.home} variant="secondary"
            onPress={() => navigation.navigate('MainTabs', { screen: 'Home' })} style={styles.action} />
          <Button title={t.charging.scanAgain}
            onPress={() => navigation.navigate('MainTabs', { screen: 'Scan' })} style={styles.action} />
        </View>
      </Card>
    </Screen>
  );
};

const styles = StyleSheet.create({
  container: { justifyContent: 'center', padding: spacing.lg },
  card: { padding: spacing.lg },
  statusBadge: { alignSelf: 'center', marginBottom: spacing.md },
  title: { fontSize: typography.title, fontWeight: typography.bold, color: COLORS.TEXT_PRIMARY, textAlign: 'center', marginBottom: 8 },
  subTitle: { fontSize: 14, color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },
  block: { marginTop: 12 },
  kvTitle: { fontSize: 16, fontWeight: '600', marginBottom: 4 },
  kv: { fontSize: 14, color: COLORS.TEXT_PRIMARY, marginTop: 4 },
  notice: { marginTop: 12, padding: 12, backgroundColor: COLORS.IOS_LIGHT_GRAY, borderRadius: radius.md },
  noticeText: { fontSize: 13, color: COLORS.TEXT_SECONDARY },
  settleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  settleText: { marginLeft: 8, color: COLORS.TEXT_SECONDARY },
  errorText: { color: COLORS.ERROR, marginTop: 8 },
  row: { flexDirection: 'row', marginTop: 24, gap: 12 },
  action: { flex: 1 },
});

export default ChargingCompleteScreen;
