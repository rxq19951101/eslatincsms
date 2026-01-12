/**
 * 充电完成页（仅支持扫码充电）
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { settleCharging, SettleResult } from '../../api/charging';
import { fetchWalletBalance, fetchWalletTransactions } from '../../store/slices/walletSlice';

type R = RouteProp<RootStackParamList, 'ChargingComplete'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingComplete'>;

const ChargingCompleteScreen = () => {
  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();
  const { chargePointId } = route.params;

  const dispatch = useAppDispatch();
  const { lastStoppedSession, lastRemoteResult } = useAppSelector((s) => s.charging);

  const [settling, setSettling] = useState(false);
  const [settleResult, setSettleResult] = useState<SettleResult | null>(null);
  const [settleError, setSettleError] = useState<string | null>(null);

  useEffect(() => {
    // 有 session 才能结算；结算幂等，多次调用不会重复扣费
    if (!lastStoppedSession) return;
    let cancelled = false;
    (async () => {
      try {
        setSettling(true);
        setSettleError(null);
        const res = await settleCharging(lastStoppedSession.id);
        if (cancelled) return;
        setSettleResult(res);
        // 刷新钱包展示
        dispatch(fetchWalletBalance());
        dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
      } catch (e: any) {
        if (cancelled) return;
        const msg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '结算失败';
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
        <Text style={styles.title}>充电已结束</Text>
        <Text style={styles.subTitle}>充电桩：{chargePointId}</Text>

        {lastStoppedSession && (
          <View style={styles.block}>
            <Text style={styles.kv}>会话ID：{lastStoppedSession.id}</Text>
            <Text style={styles.kv}>TransactionId：{lastStoppedSession.transaction_id}</Text>
          </View>
        )}

        {lastRemoteResult && (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              {lastRemoteResult.success ? '停止请求已发送：' : '停止请求失败：'}
              {lastRemoteResult.message}
            </Text>
          </View>
        )}

        <View style={styles.block}>
          <Text style={styles.kvTitle}>结算</Text>
          {settling && (
            <View style={styles.settleRow}>
              <ActivityIndicator size="small" color={COLORS.PRIMARY} />
              <Text style={styles.settleText}>结算中...</Text>
            </View>
          )}
          {!!settleError && <Text style={styles.errorText}>{settleError}</Text>}
          {!!settleResult && (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.kv}>
                {settleResult.already_settled ? '已结算过' : '本次扣费'}：$
                {settleResult.charged_amount.toFixed(2)}
              </Text>
              <Text style={styles.kv}>
                余额：${settleResult.balance.toFixed(2)} {settleResult.currency}
              </Text>
              {typeof settleResult.energy_kwh === 'number' && (
                <Text style={styles.kv}>电量：{settleResult.energy_kwh.toFixed(3)} kWh</Text>
              )}
              {typeof settleResult.price_per_kwh === 'number' && (
                <Text style={styles.kv}>电价：${settleResult.price_per_kwh.toFixed(2)}/kWh</Text>
              )}
            </View>
          )}
        </View>

        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.secondary]}
            onPress={() => navigation.navigate('MainTabs')}
          >
            <Text style={styles.secondaryText}>返回首页</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.primary]}
            onPress={() => navigation.navigate('MainTabs')}
          >
            <Text style={styles.primaryText}>继续扫码</Text>
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND, padding: 16, justifyContent: 'center' },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  icon: { fontSize: 56, textAlign: 'center', marginBottom: 10 },
  title: { fontSize: 20, fontWeight: '900', color: COLORS.TEXT_PRIMARY, textAlign: 'center' },
  subTitle: { marginTop: 8, color: COLORS.TEXT_SECONDARY, textAlign: 'center' },
  block: { marginTop: 14 },
  kvTitle: { color: COLORS.TEXT_SECONDARY, fontWeight: '900', marginBottom: 6 },
  kv: { color: COLORS.TEXT_PRIMARY, fontWeight: '700', marginTop: 6 },
  notice: { marginTop: 14, backgroundColor: '#ECFDF5', borderRadius: 12, padding: 10 },
  noticeText: { color: '#065F46', fontWeight: '700' },
  settleRow: { flexDirection: 'row', alignItems: 'center', marginTop: 6 },
  settleText: { marginLeft: 10, color: COLORS.TEXT_SECONDARY },
  errorText: { marginTop: 6, color: COLORS.ERROR, fontWeight: '800' },
  row: { flexDirection: 'row', marginTop: 18 },
  btn: { flex: 1, height: 46, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  secondary: { backgroundColor: '#E5E7EB', marginRight: 10 },
  secondaryText: { color: COLORS.TEXT_PRIMARY, fontWeight: '900' },
  primary: { backgroundColor: COLORS.PRIMARY },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
});

export default ChargingCompleteScreen;

