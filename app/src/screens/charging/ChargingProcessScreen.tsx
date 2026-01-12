/**
 * 充电过程页（仅支持扫码充电）
 * - 发送 RemoteStart
 * - 轮询 /app/charging/active 获取 transactionId / 会话信息
 * - 支持结束充电（RemoteStop）
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchActiveSession, fetchMeterValuePoints, setChargingTarget, startCharging, stopChargingSession } from '../../store/slices/chargingSlice';

type R = RouteProp<RootStackParamList, 'ChargingProcess'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingProcess'>;

const ChargingProcessScreen = () => {
  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();

  const { chargePointId, connectorId } = route.params;
  const { starting, stopping, loadingActive, activeSession, error, lastRemoteResult, meterValues, lastMeterId, loadingMeter, meterError } = useAppSelector(
    (s) => s.charging
  );

  const [stopRequested, setStopRequested] = useState(false);
  const [hasEverActive, setHasEverActive] = useState(false);
  const [autoStarted, setAutoStarted] = useState(false);

  useEffect(() => {
    dispatch(setChargingTarget({ chargePointId, connectorId }));
    dispatch(fetchActiveSession(chargePointId));
  }, [dispatch, chargePointId, connectorId]);

  // 进入页面自动发送启动请求（扫码后无需用户再点“开始”）
  useEffect(() => {
    if (autoStarted) return;
    setAutoStarted(true);
    (async () => {
      try {
        await dispatch(startCharging({ chargePointId, connectorId })).unwrap();
      } catch {
        // 错误已写入 slice.error
      }
    })();
  }, [autoStarted, dispatch, chargePointId, connectorId]);

  useEffect(() => {
    if (activeSession) setHasEverActive(true);
  }, [activeSession]);

  // 轮询 active session（RemoteStart 后需要等待桩上报 StartTransaction 才会入库）
  useEffect(() => {
    const t = setInterval(() => {
      dispatch(fetchActiveSession(chargePointId));
    }, 3000);
    return () => clearInterval(t);
  }, [dispatch, chargePointId]);

  // 有 session 后轮询 meter values（增量拉取）
  useEffect(() => {
    if (!activeSession?.id) return;
    // 先立即拉一次
    dispatch(fetchMeterValuePoints({ sessionId: activeSession.id, sinceId: lastMeterId || undefined }));
    const t = setInterval(() => {
      dispatch(fetchMeterValuePoints({ sessionId: activeSession.id, sinceId: lastMeterId || undefined }));
    }, 3000);
    return () => clearInterval(t);
    // 依赖 activeSession.id 与 lastMeterId（增量）
  }, [dispatch, activeSession?.id, lastMeterId]);

  // stop 后：当 activeSession 从“有”变成“无”，认为已结束（至少协议会话已不再 ongoing）
  useEffect(() => {
    if (stopRequested && hasEverActive && !activeSession) {
      navigation.replace('ChargingComplete', { chargePointId });
    }
  }, [stopRequested, hasEverActive, activeSession, navigation, chargePointId]);

  const startedText = useMemo(() => {
    if (!activeSession?.start_time) return '—';
    try {
      return new Date(activeSession.start_time).toLocaleString();
    } catch {
      return activeSession.start_time;
    }
  }, [activeSession?.start_time]);

  const latestPoint = useMemo(() => {
    if (!meterValues || meterValues.length === 0) return null;
    return meterValues[meterValues.length - 1];
  }, [meterValues]);

  const sessionEnergyKwh = useMemo(() => {
    if (!activeSession || !latestPoint) return null;
    const meterStart = (activeSession as any).meter_start;
    if (typeof meterStart !== 'number') return latestPoint.energy_kwh;
    const deltaWh = latestPoint.value_wh - meterStart;
    if (!Number.isFinite(deltaWh)) return latestPoint.energy_kwh;
    return Math.max(0, deltaWh) / 1000.0;
  }, [activeSession, latestPoint]);

  const canStop = !!activeSession && !stopRequested;

  const onRetryStart = async () => {
    try {
      await dispatch(startCharging({ chargePointId, connectorId })).unwrap();
    } catch {
      // 错误已写入 slice.error
    }
  };

  const onStop = async () => {
    try {
      setStopRequested(true);
      await dispatch(stopChargingSession(chargePointId)).unwrap();
    } catch {
      // stop 失败则允许用户重试
      setStopRequested(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>充电中</Text>
        <View style={styles.headerRight} />
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>充电桩</Text>
        <Text style={styles.value}>{chargePointId}</Text>

        <View style={styles.row}>
          <View style={styles.col}>
            <Text style={styles.label}>接口</Text>
            <Text style={styles.valueSmall}>{connectorId}</Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.label}>会话ID</Text>
            <Text style={styles.valueSmall}>{activeSession ? String(activeSession.id) : '等待中…'}</Text>
          </View>
        </View>

        <View style={styles.row}>
          <View style={styles.col}>
            <Text style={styles.label}>TransactionId</Text>
            <Text style={styles.valueSmall}>
              {activeSession ? String(activeSession.transaction_id) : '等待桩上报…'}
            </Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.label}>开始时间</Text>
            <Text style={styles.valueSmall}>{activeSession ? startedText : '—'}</Text>
          </View>
        </View>

        {!!lastRemoteResult && (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              {lastRemoteResult.success ? '已发送控制请求：' : '控制请求失败：'}
              {lastRemoteResult.message}
            </Text>
          </View>
        )}

        {(starting || stopping || loadingActive) && (
          <View style={styles.loadingLine}>
            <ActivityIndicator size="small" color={COLORS.PRIMARY} />
            <Text style={styles.loadingText}>
              {starting ? '正在发送启动请求…' : stopping ? '正在发送停止请求…' : '正在同步会话…'}
            </Text>
          </View>
        )}

        {!!error && <Text style={styles.errorText}>{error}</Text>}
      </View>

      {/* 实时数据 */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>实时数据</Text>

        {!activeSession && (
          <Text style={styles.mutedText}>等待生成会话后才会有实时数据（桩上报 MeterValues）。</Text>
        )}

        {!!meterError && <Text style={styles.errorText}>{meterError}</Text>}

        {activeSession && !latestPoint && !loadingMeter && (
          <Text style={styles.mutedText}>暂无实时数据（可能桩未上报 MeterValues）。</Text>
        )}

        {(loadingMeter || loadingActive) && (
          <View style={styles.loadingLine}>
            <ActivityIndicator size="small" color={COLORS.PRIMARY} />
            <Text style={styles.loadingText}>同步实时数据...</Text>
          </View>
        )}

        {!!latestPoint && (
          <>
            <View style={styles.row}>
              <View style={styles.col}>
                <Text style={styles.label}>已充电量</Text>
                <Text style={styles.valueSmall}>
                  {typeof sessionEnergyKwh === 'number' ? `${sessionEnergyKwh.toFixed(3)} kWh` : '—'}
                </Text>
              </View>
              <View style={styles.col}>
                <Text style={styles.label}>功率</Text>
                <Text style={styles.valueSmall}>
                  {typeof latestPoint.power_kw === 'number' ? `${latestPoint.power_kw.toFixed(2)} kW` : '—'}
                </Text>
              </View>
            </View>
            <View style={styles.row}>
              <View style={styles.col}>
                <Text style={styles.label}>电流</Text>
                <Text style={styles.valueSmall}>
                  {typeof latestPoint.current_a === 'number' ? `${latestPoint.current_a.toFixed(1)} A` : '—'}
                </Text>
              </View>
              <View style={styles.col}>
                <Text style={styles.label}>电压</Text>
                <Text style={styles.valueSmall}>
                  {typeof latestPoint.voltage_v === 'number' ? `${latestPoint.voltage_v.toFixed(0)} V` : '—'}
                </Text>
              </View>
            </View>
            <View style={styles.row}>
              <View style={styles.col}>
                <Text style={styles.label}>SoC</Text>
                <Text style={styles.valueSmall}>
                  {typeof latestPoint.soc === 'number' ? `${latestPoint.soc.toFixed(0)}%` : '—'}
                </Text>
              </View>
              <View style={styles.col}>
                <Text style={styles.label}>采样点</Text>
                <Text style={styles.valueSmall}>{meterValues.length}</Text>
              </View>
            </View>

            <View style={styles.pointsBox}>
              <Text style={styles.pointsTitle}>最近采样</Text>
              {meterValues.slice(-8).map((p) => (
                <View key={p.id} style={styles.pointRow}>
                  <Text style={styles.pointText}>
                    {p.timestamp ? new Date(p.timestamp).toLocaleTimeString() : '—'}
                  </Text>
                  <Text style={styles.pointText}>{Math.round(p.value_wh)} Wh</Text>
                  <Text style={styles.pointText}>
                    {typeof p.power_kw === 'number' ? `${p.power_kw.toFixed(2)} kW` : '—'}
                  </Text>
                </View>
              ))}
            </View>
          </>
        )}
      </View>

      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={[styles.btn, styles.primary, (starting || stopRequested) && styles.disabled]}
          disabled={starting || stopRequested}
          onPress={onRetryStart}
        >
          <Text style={styles.primaryText}>{starting ? '启动中…' : '重试启动'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.btn, styles.danger, (!canStop || stopping) && styles.disabled]}
          disabled={!canStop || stopping}
          onPress={onStop}
        >
          <Text style={styles.dangerText}>{stopRequested ? '等待结束…' : '结束充电'}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: {
    height: 56,
    backgroundColor: '#FFFFFF',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.BORDER,
  },
  backBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 22, color: COLORS.TEXT_PRIMARY },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  headerRight: { width: 44 },

  card: {
    margin: 16,
    padding: 16,
    borderRadius: 14,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  title: { fontSize: 12, color: COLORS.TEXT_SECONDARY, marginBottom: 6 },
  value: { fontSize: 18, fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  row: { flexDirection: 'row', marginTop: 14 },
  col: { flex: 1 },
  label: { fontSize: 12, color: COLORS.TEXT_SECONDARY, marginBottom: 4 },
  valueSmall: { fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  sectionTitle: { fontSize: 14, fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  mutedText: { marginTop: 10, color: COLORS.TEXT_SECONDARY, lineHeight: 18 },

  notice: { marginTop: 14, backgroundColor: '#ECFDF5', borderRadius: 12, padding: 10 },
  noticeText: { color: '#065F46', fontWeight: '700' },

  loadingLine: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  loadingText: { marginLeft: 10, color: COLORS.TEXT_SECONDARY },
  errorText: { marginTop: 10, color: COLORS.ERROR, fontWeight: '700' },

  pointsBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: COLORS.BORDER, paddingTop: 10 },
  pointsTitle: { color: COLORS.TEXT_SECONDARY, fontWeight: '900', marginBottom: 6 },
  pointRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  pointText: { color: COLORS.TEXT_SECONDARY, fontSize: 12 },

  bottomBar: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  btn: { flex: 1, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY, marginRight: 10 },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
  danger: { backgroundColor: COLORS.ERROR },
  dangerText: { color: '#FFFFFF', fontWeight: '900' },
  disabled: { opacity: 0.5 },
});

export default ChargingProcessScreen;

