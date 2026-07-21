/**
 * 充电过程页（仅支持扫码充电）
 * - 先检查充电桩状态（离线/正在充电/可充电）
 * - 根据状态显示不同的交互界面
 * - 可充电时让用户确认后发送 RemoteStart
 * - 显示充电过程和实时数据
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  Alert,
  AppState,
  type AppStateStatus,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useIsFocused, useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS, IOS_STYLES, PAYMENT_RAILS_ENABLED, MIN_BALANCE_COP } from '../../constants/config';
import { useI18n } from '../../i18n';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import CircularProgress from '../../components/ui/CircularProgress';
import Skeleton from '../../components/ui/Skeleton';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Badge from '../../components/ui/Badge';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchActiveSession, fetchMeterValuePoints, setChargingTarget, startCharging, stopChargingSession } from '../../store/slices/chargingSlice';
import { checkChargerStatus, type ChargerStatusCheck } from '../../api/charging';
import { PaymentMethodBar } from '../../components/payment/PaymentMethodBar';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import { formatDateTime, localizeChargingFailure, publicChargerIdentity } from '../../utils/localizedDisplay';

type R = RouteProp<RootStackParamList, 'ChargingProcess'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingProcess'>;

type ChargerStatus = 'checking' | 'offline' | 'charging_other' | 'charging_self' | 'available';

const ChargingProcessScreen = () => {
  const { t, locale } = useI18n();

  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();
  const isFocused = useIsFocused();
  const dispatch = useAppDispatch();

  const { qrToken, sessionId: routeSessionId } = route.params;
  const { starting, stopping, activeSession, error, meterValues, lastMeterId, meterError } = useAppSelector(
    (s) => s.charging
  );
  const { balance: walletBalanceSlice, loadingBalance } = useAppSelector((s) => s.wallet);

  const [chargerStatus, setChargerStatus] = useState<ChargerStatus>(qrToken ? 'checking' : 'charging_self');
  const [statusCheckData, setStatusCheckData] = useState<ChargerStatusCheck | null>(null);
  const [statusCheckError, setStatusCheckError] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);
  const [hasEverActive, setHasEverActive] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const startRequestInFlight = useRef(false);
  const lastActiveIdentity = useRef<string | null>(activeSession?.ocpp_identity || null);
  const lastMeterIdRef = useRef<string | null>(lastMeterId);
  const [appState, setAppState] = useState<AppStateStatus>(AppState.currentState ?? 'active');
  const pollingEnabled = isFocused && appState !== 'background' && appState !== 'inactive';

  useEffect(() => {
    const subscription = AppState.addEventListener('change', setAppState);
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    lastMeterIdRef.current = lastMeterId;
  }, [lastMeterId]);

  const chargingErrorText = useMemo(() => localizeChargingFailure(error, t), [error, t]);
  const meterErrorText = useMemo(() => localizeChargingFailure(meterError, t), [meterError, t]);

  const latestPoint = useMemo(() => {
    if (!meterValues || meterValues.length === 0) return null;
    return meterValues[meterValues.length - 1];
  }, [meterValues]);

  useEffect(() => {
    dispatch(fetchWalletBalance());
  }, [dispatch]);

  // 页面加载时先检查充电桩状态
  useEffect(() => {
    if (!qrToken) {
      setChargerStatus('charging_self');
      return;
    }
    const checkStatus = async () => {
      try {
        setStatusCheckError(null);
        const data = await checkChargerStatus(qrToken);
        setStatusCheckData(data);
        
        // 根据状态设置页面状态
        if (!data.is_online) {
          setChargerStatus('offline');
        } else if (data.active_session) {
          if (data.active_session.is_current_user) {
            setChargerStatus('charging_self');
            dispatch(setChargingTarget({ qrToken }));
          } else {
            setChargerStatus('charging_other');
          }
        } else {
          setChargerStatus('available');
        }
      } catch (e: any) {
        console.error('检查充电桩状态失败:', e);
        // 提取更详细的错误信息
        let errorMsg = t.chargingUi.checkFailed;
        if (e?.response?.status === 404) {
          errorMsg = t.chargingUi.notFoundOrQr;
        } else if (e?.response?.status === 400) errorMsg = t.chargingUi.invalidQr;
        setStatusCheckError(errorMsg);
        setChargerStatus('offline'); // 默认显示离线状态
      }
    };

    checkStatus();
  }, [qrToken, dispatch]);

  // 当前用户正在充电：设置并开始轮询
  useEffect(() => {
    if (chargerStatus === 'charging_self' && pollingEnabled) {
      if (qrToken) dispatch(setChargingTarget({ qrToken }));
      dispatch(fetchActiveSession(qrToken));
    }
  }, [chargerStatus, qrToken, dispatch, pollingEnabled]);

  useEffect(() => {
    if (activeSession) {
      lastActiveIdentity.current = activeSession.ocpp_identity || lastActiveIdentity.current;
      setHasEverActive(true);
      setIsInitialLoad(false);
      // 如果之前是 available 状态，现在有会话了，切换到 charging_self
      if (chargerStatus === 'available') {
        setChargerStatus('charging_self');
      }
    }
  }, [activeSession, chargerStatus]);

  // 首次数据加载完成后，取消初始加载状态
  useEffect(() => {
    if (activeSession && latestPoint) {
      setIsInitialLoad(false);
    }
  }, [activeSession, latestPoint]);

  // 轮询 active session（当前用户正在充电时）
  useEffect(() => {
    if (chargerStatus !== 'charging_self' || !pollingEnabled) return;
    const activePollDelay = error?.operation === 'active' && error.status === 429
      ? 30000
      : stopRequested
        ? 2000
        : 10000;
    const t = setInterval(() => {
      dispatch(fetchActiveSession(qrToken));
    }, activePollDelay);
    return () => clearInterval(t);
  }, [chargerStatus, dispatch, error?.operation, error?.status, pollingEnabled, qrToken, stopRequested]);

  // session 首次出现时立即读取一次计量值。
  useEffect(() => {
    if (!activeSession?.id || chargerStatus !== 'charging_self' || !pollingEnabled) return;
    dispatch(fetchMeterValuePoints({
      sessionId: activeSession.id,
      sinceId: lastMeterIdRef.current || undefined,
    }));
  }, [dispatch, activeSession?.id, chargerStatus, pollingEnabled]);

  // 增量轮询读取 ref 中的最新游标，避免游标变化时重建定时器并立刻重复请求。
  useEffect(() => {
    if (!activeSession?.id || chargerStatus !== 'charging_self' || !pollingEnabled) return;
    const meterPollDelay = meterError?.status === 429 ? 30000 : 5000;
    const t = setInterval(() => {
      dispatch(fetchMeterValuePoints({
        sessionId: activeSession.id,
        sinceId: lastMeterIdRef.current || undefined,
      }));
    }, meterPollDelay);
    return () => clearInterval(t);
  }, [dispatch, activeSession?.id, chargerStatus, meterError?.status, pollingEnabled]);

  // stop 后：当 activeSession 从"有"变成"无"，认为已结束
  useEffect(() => {
    if (stopRequested && hasEverActive && !activeSession) {
      navigation.replace('ChargingComplete', {
        ocppIdentity: lastActiveIdentity.current || statusCheckData?.ocpp_identity || undefined,
      });
    }
  }, [stopRequested, hasEverActive, activeSession, navigation, statusCheckData]);

  const startedText = useMemo(() => {
    if (!activeSession?.start_time) return '—';
    try {
      return formatDateTime(activeSession.start_time, locale);
    } catch {
      return activeSession.start_time;
    }
  }, [activeSession?.start_time, locale]);

  const sessionEnergyKwh = useMemo(() => {
    if (!activeSession || !latestPoint) return null;
    const meterStart = (activeSession as any).meter_start;
    if (typeof meterStart !== 'number') return latestPoint.energy_kwh;
    const deltaWh = latestPoint.value_wh - meterStart;
    if (!Number.isFinite(deltaWh)) return latestPoint.energy_kwh;
    return Math.max(0, deltaWh) / 1000.0;
  }, [activeSession, latestPoint]);

  // 计算充电时长（必须在所有早期返回之前定义）
  const timeText = useMemo(() => {
    if (!activeSession?.start_time) return '';
    try {
      const startTime = new Date(activeSession.start_time).getTime();
      const now = Date.now();
      const minutes = Math.max(0, Math.round((now - startTime) / 1000 / 60));
      return t.chargingUi.minutesCharged.replace('{n}', String(minutes));
    } catch {
      return '';
    }
  }, [activeSession?.start_time]);

  const canStop = !!activeSession && !stopRequested && chargerStatus === 'charging_self';
  const showRetryStart = chargerStatus === 'available' && !starting && !stopRequested;
  const showWaitingSession =
    chargerStatus === 'charging_self' && !activeSession && !stopRequested && !starting;

  const submitStartOnce = async () => {
    if (!qrToken || startRequestInFlight.current || starting) return;
    startRequestInFlight.current = true;
    try {
      await dispatch(startCharging({ qrToken })).unwrap();
      setChargerStatus('charging_self');
    } catch {
      // Stable error semantics are localized from the slice during render.
    } finally {
      startRequestInFlight.current = false;
    }
  };

  const onStartCharging = () => {
    const bal = walletBalanceSlice?.balance ?? 0;
    if (bal < MIN_BALANCE_COP) {
      Alert.alert(
        t.charging.insufficientBalance,
        PAYMENT_RAILS_ENABLED
          ? t.chargingUi.needTopUp.replace('{amount}', MIN_BALANCE_COP.toLocaleString())
          : t.chargingUi.needBalance.replace('{amount}', MIN_BALANCE_COP.toLocaleString()),
        PAYMENT_RAILS_ENABLED
          ? [
              { text: t.chargingUi.goTopUp, onPress: () => navigation.navigate('PaymentHub') },
              { text: t.common.cancel, style: 'cancel' },
            ]
          : [{ text: t.chargingUi.understood, style: 'cancel' }]
      );
      return;
    }
    void submitStartOnce();
  };

  const onRetryStart = () => void submitStartOnce();

  const onStop = async () => {
    const sessionId = activeSession?.id || routeSessionId;
    if (!sessionId) return;
    try {
      setStopRequested(true);
      await dispatch(stopChargingSession(sessionId)).unwrap();
    } catch {
      setStopRequested(false);
    }
  };

  const onRefreshStatus = async () => {
    if (!qrToken) {
      dispatch(fetchActiveSession(undefined));
      return;
    }
    setChargerStatus('checking');
    setStatusCheckError(null);
    try {
      const data = await checkChargerStatus(qrToken);
      setStatusCheckData(data);
      
      if (!data.is_online) {
        setChargerStatus('offline');
      } else if (data.active_session) {
        if (data.active_session.is_current_user) {
          setChargerStatus('charging_self');
          dispatch(setChargingTarget({ qrToken }));
        } else {
          setChargerStatus('charging_other');
        }
      } else {
        setChargerStatus('available');
      }
    } catch (e: any) {
      console.error('刷新状态失败:', e);
      let errorMsg = t.chargingUi.refreshFailed;
      if (e?.response?.status === 404) {
        errorMsg = t.chargingUi.notFoundOrQr;
      } else if (e?.response?.status === 400) errorMsg = t.chargingUi.invalidQr;
      setStatusCheckError(errorMsg);
    }
  };

  // 渲染：检查状态中
  if (chargerStatus === 'checking') {
    return (
      <SafeAreaView testID="app-charging-checking" accessibilityLabel={t.chargingUi.checkingMsg} style={styles.container}>
        <ScreenHeader title={t.chargingUi.statusTitle} onBack={() => navigation.goBack()} />
        <View style={styles.centerContent}>
          <LoadingSpinner size="large" message={t.chargingUi.checkingMsg} />
        </View>
      </SafeAreaView>
    );
  }

  // 渲染：离线状态
  if (chargerStatus === 'offline') {
    return (
      <SafeAreaView testID="app-charging-offline" accessibilityLabel={t.chargingUi.offlineTitle} style={styles.container}>
        <ScreenHeader title={t.chargingUi.offlineTitle} onBack={() => navigation.goBack()} />
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Badge label={t.chargingUi.offlineTitle} variant="error" />
              <Text style={styles.statusTitle}>{t.chargingUi.offlineTitle}</Text>
              <Text style={styles.statusSubtitle}>{t.chargingUi.offlineSub}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>{t.chargingUi.chargerId}</Text>
              <Text style={styles.infoValue}>{publicChargerIdentity(statusCheckData)}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>{t.chargingUi.lastOnline}</Text>
              <Text style={styles.infoValue}>
                {statusCheckData?.last_seen
                  ? formatDateTime(statusCheckData.last_seen, locale)
                  : t.chargingUi.neverOnline}
              </Text>
            </View>

            {statusCheckError && (
              <View testID="app-charging-check-error" accessibilityRole="alert" style={styles.errorNotice}>
                <Text style={styles.errorText}>{statusCheckError}</Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                testID="app-charging-check-retry"
                title={t.chargingUi.refreshStatus}
                onPress={onRefreshStatus}
                variant="outline"
                style={styles.refreshButton}
              />
              <Button
                title={t.common.back}
                onPress={() => navigation.goBack()}
                variant="secondary"
                style={styles.returnButton}
              />
            </View>
          </Card>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // 渲染：其他用户正在充电
  if (chargerStatus === 'charging_other') {
    return (
      <SafeAreaView testID="app-charging-in-use" accessibilityLabel={t.chargingUi.inUseTitle} style={styles.container}>
        <ScreenHeader title={t.chargingUi.inUseTitle} onBack={() => navigation.goBack()} />
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Badge label={t.chargingUi.inUseTitle} variant="warning" />
              <Text style={styles.statusTitle}>{t.chargingUi.inUseTitle}</Text>
              <Text style={styles.statusSubtitle}>{t.chargingUi.inUseSub}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>{t.chargingUi.chargerId}</Text>
              <Text style={styles.infoValue}>{publicChargerIdentity(statusCheckData)}</Text>
            </View>

            {statusCheckData?.charger_info?.site_name && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>{t.chargingUi.siteName}</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_name}</Text>
              </View>
            )}

            {statusCheckData?.active_session?.start_time && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>{t.chargingUi.chargeStart}</Text>
                <Text style={styles.infoValue}>
                  {formatDateTime(statusCheckData.active_session.start_time, locale)}
                </Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                testID="app-charging-check-retry"
                title={t.chargingUi.refreshStatus}
                onPress={onRefreshStatus}
                variant="outline"
                style={styles.refreshButton}
              />
              <Button
                title={t.common.back}
                onPress={() => navigation.goBack()}
                variant="secondary"
                style={styles.returnButton}
              />
            </View>
          </Card>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // 渲染：可充电状态
  if (chargerStatus === 'available') {
    return (
      <SafeAreaView testID="app-charging-ready" accessibilityLabel={t.charging.available} style={styles.container}>
        <ScreenHeader title={t.chargingUi.readyTitle} onBack={() => navigation.goBack()} />
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Badge label={t.charging.available} variant="success" />
              <Text style={styles.statusTitle}>{t.charging.available}</Text>
              <Text style={styles.statusSubtitle}>{t.chargingUi.readySub}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>{t.chargingUi.chargerId}</Text>
              <Text style={styles.infoValue}>{publicChargerIdentity(statusCheckData)}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>{t.chargingUi.connector}</Text>
              <Text style={styles.infoValue}>{statusCheckData?.connector_id || '—'}</Text>
            </View>

            {statusCheckData?.charger_info?.site_name && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>{t.chargingUi.siteName}</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_name}</Text>
              </View>
            )}

            {statusCheckData?.charger_info?.site_address && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>{t.chargingUi.siteAddress}</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_address}</Text>
              </View>
            )}

            {statusCheckData?.charger_info?.price_per_kwh != null && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>{t.chargingUi.unitPrice}</Text>
                <Text style={styles.infoValue}>
                  $
                  {statusCheckData!.charger_info!.price_per_kwh!.toLocaleString('es-CO', {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 2,
                  })}{' '}
                  COP / kWh
                </Text>
              </View>
            )}

            <PaymentMethodBar
              balanceCOP={walletBalanceSlice?.balance ?? null}
              loading={loadingBalance}
              onPressTopUp={
                PAYMENT_RAILS_ENABLED
                  ? () => navigation.navigate('PaymentHub')
                  : undefined
              }
            />

            {chargingErrorText && (
              <View testID="app-charging-start-error" accessibilityRole="alert" style={styles.errorNotice}>
                <Text style={styles.errorText}>{chargingErrorText}</Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                testID="app-charging-start"
                title={t.charging.start}
                onPress={onStartCharging}
                variant="primary"
                disabled={starting}
                loading={starting}
                style={styles.startButton}
              />
              <Button
                title={t.common.back}
                onPress={() => navigation.goBack()}
                variant="secondary"
                style={styles.returnButton}
              />
            </View>
          </Card>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // 渲染：当前用户正在充电（重新设计）
  const progressPercentage = latestPoint?.soc ? latestPoint.soc : 0;
  const energyText = typeof sessionEnergyKwh === 'number' ? `${sessionEnergyKwh.toFixed(2)} kWh` : '—';

  return (
    <SafeAreaView testID="app-charging-active" accessibilityLabel={t.chargingUi.chargingTitle} style={styles.container}>
      <ScreenHeader title={t.chargingUi.chargingTitle} onBack={() => navigation.goBack()} />

      <ScrollView style={styles.scrollContent} contentContainerStyle={styles.scrollContentContainer}>
        {/* 充电桩信息（简化） */}
        <View style={styles.chargerInfo}>
          <Text style={styles.chargerName}>
            {publicChargerIdentity(activeSession, publicChargerIdentity(statusCheckData))}
          </Text>
          {activeSession?.start_time && (
            <Text style={styles.startTime}>{t.chargingUi.startAt.replace('{time}', startedText)}</Text>
          )}
        </View>

        {/* 首次加载时显示骨架屏 */}
        {isInitialLoad && (!activeSession || !latestPoint) ? (
          <View style={styles.skeletonContainer}>
            <Skeleton width={200} height={200} borderRadius={100} style={styles.skeletonCircle} />
            <View style={styles.skeletonInfo}>
              <Skeleton width="60%" height={24} style={{ marginBottom: 12 }} />
              <Skeleton width="40%" height={16} />
            </View>
            <View style={styles.skeletonDataGrid}>
              <Skeleton width={80} height={60} borderRadius={12} />
              <Skeleton width={80} height={60} borderRadius={12} />
              <Skeleton width={80} height={60} borderRadius={12} />
              <Skeleton width={80} height={60} borderRadius={12} />
            </View>
          </View>
        ) : (
          <>
            {/* 弧形进度圈 */}
            <View style={styles.progressContainer}>
              <CircularProgress
                progress={progressPercentage}
                size={220}
                strokeWidth={14}
                progressColor={COLORS.PRIMARY}
                mainText={energyText}
                subText={timeText}
                bottomInfo={[
                  {
                    label: t.chargingUi.power,
                    value: typeof latestPoint?.power_kw === 'number' 
                      ? `${latestPoint.power_kw.toFixed(2)} kW` 
                      : '—',
                  },
                  {
                    label: 'SoC',
                    value: typeof latestPoint?.soc === 'number' 
                      ? `${latestPoint.soc.toFixed(0)}%` 
                      : '—',
                  },
                ]}
              />
            </View>

            {/* 实时数据网格 */}
            {latestPoint && (
              <Card testID="app-charging-meter" accessibilityLabel={t.chargingUi.waitingData} style={styles.dataCard}>
                <View style={styles.dataGrid}>
                  <View style={styles.dataItem}>
                    <Text style={styles.dataLabel}>{t.chargingUi.voltage}</Text>
                    <Text style={styles.dataValue}>
                      {typeof latestPoint.voltage_v === 'number' 
                        ? `${latestPoint.voltage_v.toFixed(0)} V` 
                        : '—'}
                    </Text>
                  </View>
                  <View style={styles.dataItem}>
                    <Text style={styles.dataLabel}>{t.chargingUi.current}</Text>
                    <Text style={styles.dataValue}>
                      {typeof latestPoint.current_a === 'number' 
                        ? `${latestPoint.current_a.toFixed(1)} A` 
                        : '—'}
                    </Text>
                  </View>
                </View>
              </Card>
            )}

            {/* 无数据提示 */}
            {!latestPoint && activeSession && !isInitialLoad && (
              <Card style={styles.infoCard}>
                <Text style={styles.infoText}>{t.chargingUi.waitingData}</Text>
              </Card>
            )}

            {/* 错误提示 */}
            {(chargingErrorText || meterErrorText) && (
              <Card testID="app-charging-error" accessibilityLabel={chargingErrorText || meterErrorText || undefined} style={styles.errorCard}>
                <Text style={styles.errorText}>{chargingErrorText || meterErrorText}</Text>
              </Card>
            )}

            {/* 控制请求状态（仅在启动/停止时显示） */}
            {(starting || stopping) && (
              <Card style={styles.statusCard}>
                <View style={styles.statusRow}>
                  <ActivityIndicator size="small" color={COLORS.PRIMARY} />
                  <Text style={styles.statusText}>
                    {starting ? t.chargingUi.starting : stopping ? t.chargingUi.stopping : ''}
                  </Text>
                </View>
              </Card>
            )}
          </>
        )}
      </ScrollView>

      {/* 底部操作按钮 */}
      <View style={styles.bottomBar}>
        {!stopRequested && canStop && (
          <Button
            testID="app-charging-stop"
            title={stopping ? t.chargingUi.stopping : t.chargingUi.endCharge}
            onPress={onStop}
            variant="danger"
            disabled={stopping || !canStop}
            style={styles.stopButton}
          />
        )}
        {!canStop && showRetryStart && (
          <Button
            testID="app-charging-start-retry"
            title={starting ? t.charging.starting : t.charging.retryStart}
            onPress={onRetryStart}
            variant="primary"
            disabled={starting}
            loading={starting}
            style={styles.retryButton}
          />
        )}
        {showWaitingSession && (
          <View testID="app-charging-active-waiting" style={styles.waitingContainer}>
            <ActivityIndicator size="small" color={COLORS.PRIMARY} />
            <Text style={styles.waitingText}>{t.charging.waitingSession}</Text>
          </View>
        )}
        {stopRequested && (
          <View testID="app-charging-stop-waiting" style={styles.waitingContainer}>
            <ActivityIndicator size="small" color={COLORS.PRIMARY} />
            <Text style={styles.waitingText}>{t.chargingUi.waitingEnd}</Text>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  scrollContent: { flex: 1 },
  scrollContentContainer: { paddingBottom: 100 },
  centerContent: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  
  // 新的充电中页面样式
  chargerInfo: {
    alignItems: 'center',
    paddingVertical: 16,
    paddingHorizontal: 16,
  },
  chargerName: {
    fontSize: 18,
    fontWeight: '900',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 4,
  },
  startTime: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  progressContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 24,
  },
  skeletonContainer: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  skeletonCircle: {
    marginBottom: 24,
  },
  skeletonInfo: {
    width: '100%',
    alignItems: 'center',
    marginBottom: 24,
  },
  skeletonDataGrid: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 12,
    width: '100%',
    paddingHorizontal: 16,
  },
  dataCard: {
    marginHorizontal: 16,
    marginBottom: 16,
  },
  dataGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    gap: 16,
  },
  dataItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 12,
  },
  dataLabel: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: 8,
  },
  dataValue: {
    fontSize: 18,
    fontWeight: '900',
    color: COLORS.TEXT_PRIMARY,
  },
  infoCard: {
    marginHorizontal: 16,
    marginBottom: 16,
    alignItems: 'center',
    paddingVertical: 20,
  },
  infoText: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  errorCard: {
    marginHorizontal: 16,
    marginBottom: 16,
    backgroundColor: '#FEE2E2',
    padding: 16,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
  },
  statusCard: {
    marginHorizontal: 16,
    marginBottom: 16,
    padding: 12,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusText: {
    marginLeft: 12,
    fontSize: 14,
    color: COLORS.TEXT_PRIMARY,
  },
  waitingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
  },
  waitingText: {
    marginLeft: 12,
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
  },

  card: {
    margin: 16,
    padding: 16,
  },
  statusHeader: {
    alignItems: 'center',
    marginBottom: 24,
  },
  statusTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: COLORS.TEXT_PRIMARY,
    marginTop: 12,
  },
  statusSubtitle: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    marginTop: 4,
  },
  infoSection: {
    marginBottom: 16,
  },
  infoLabel: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: 4,
  },
  infoValue: {
    fontSize: 16,
    fontWeight: '800',
    color: COLORS.TEXT_PRIMARY,
  },
  actionButtons: {
    marginTop: 24,
    gap: 12,
  },
  refreshButton: {
    marginBottom: 8,
  },
  returnButton: {
    marginTop: 0,
  },
  startButton: {
    marginBottom: 8,
  },
  errorNotice: {
    marginTop: 12,
    padding: 12,
    backgroundColor: '#FEE2E2',
    borderRadius: 8,
  },
  errorText: {
    color: COLORS.ERROR,
    fontWeight: '700',
  },

  bottomBar: {
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  stopButton: {
    width: '100%',
  },
  retryButton: {
    width: '100%',
  },
});

export default ChargingProcessScreen;
