/**
 * 充电过程页（仅支持扫码充电）
 * - 先检查充电桩状态（离线/正在充电/可充电）
 * - 根据状态显示不同的交互界面
 * - 可充电时让用户确认后发送 RemoteStart
 * - 显示充电过程和实时数据
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS, IOS_STYLES } from '../../constants/config';
import Icon from '../../components/ui/Icon';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import CircularProgress from '../../components/ui/CircularProgress';
import Skeleton from '../../components/ui/Skeleton';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchActiveSession, fetchMeterValuePoints, setChargingTarget, startCharging, stopChargingSession } from '../../store/slices/chargingSlice';
import { checkChargerStatus, type ChargerStatusCheck } from '../../api/charging';

type R = RouteProp<RootStackParamList, 'ChargingProcess'>;
type Nav = StackNavigationProp<RootStackParamList, 'ChargingProcess'>;

type ChargerStatus = 'checking' | 'offline' | 'charging_other' | 'charging_self' | 'available';

const ChargingProcessScreen = () => {
  const route = useRoute<R>();
  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();

  const { qrToken } = route.params;
  const { starting, stopping, loadingActive, activeSession, error, lastRemoteResult, meterValues, lastMeterId, loadingMeter, meterError } = useAppSelector(
    (s) => s.charging
  );

  const [chargerStatus, setChargerStatus] = useState<ChargerStatus>('checking');
  const [statusCheckData, setStatusCheckData] = useState<ChargerStatusCheck | null>(null);
  const [statusCheckError, setStatusCheckError] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);
  const [hasEverActive, setHasEverActive] = useState(false);
  const [userConfirmedStart, setUserConfirmedStart] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  // 页面加载时先检查充电桩状态
  useEffect(() => {
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
            // 如果是当前用户的会话，立即设置并开始轮询
            dispatch(setChargingTarget({ qrToken }));
            dispatch(fetchActiveSession(qrToken));
          } else {
            setChargerStatus('charging_other');
          }
        } else {
          setChargerStatus('available');
        }
      } catch (e: any) {
        console.error('检查充电桩状态失败:', e);
        // 提取更详细的错误信息
        let errorMsg = '检查充电桩状态失败';
        if (e?.response?.status === 404) {
          errorMsg = '充电桩不存在或二维码无效';
        } else if (e?.response?.status === 400) {
          errorMsg = e?.response?.data?.detail || '二维码无效';
        } else if (e?.response?.data?.detail) {
          errorMsg = e.response.data.detail;
        } else if (e?.message) {
          errorMsg = e.message;
        }
        setStatusCheckError(errorMsg);
        setChargerStatus('offline'); // 默认显示离线状态
      }
    };

    checkStatus();
  }, [qrToken, dispatch]);

  // 当前用户正在充电：设置并开始轮询
  useEffect(() => {
    if (chargerStatus === 'charging_self') {
      dispatch(setChargingTarget({ qrToken }));
      dispatch(fetchActiveSession(qrToken));
    }
  }, [chargerStatus, qrToken, dispatch]);

  // 用户确认开始充电后，发送启动请求
  useEffect(() => {
    if (chargerStatus === 'available' && userConfirmedStart && !starting) {
      dispatch(startCharging({ qrToken }));
      // 启动后切换状态为充电中，等待会话创建
      setChargerStatus('charging_self');
      setUserConfirmedStart(false);
    }
  }, [chargerStatus, userConfirmedStart, starting, qrToken, dispatch]);

  useEffect(() => {
    if (activeSession) {
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
    if (chargerStatus !== 'charging_self') return;
    
    const t = setInterval(() => {
      dispatch(fetchActiveSession(qrToken));
    }, 3000);
    return () => clearInterval(t);
  }, [chargerStatus, dispatch, qrToken]);

  // 有 session 后轮询 meter values（增量拉取）
  useEffect(() => {
    if (!activeSession?.id || chargerStatus !== 'charging_self') return;
    
    dispatch(fetchMeterValuePoints({ sessionId: activeSession.id, sinceId: lastMeterId || undefined }));
    const t = setInterval(() => {
      dispatch(fetchMeterValuePoints({ sessionId: activeSession.id, sinceId: lastMeterId || undefined }));
    }, 3000);
    return () => clearInterval(t);
  }, [dispatch, activeSession?.id, lastMeterId, chargerStatus]);

  // stop 后：当 activeSession 从"有"变成"无"，认为已结束
  useEffect(() => {
    if (stopRequested && hasEverActive && !activeSession) {
      navigation.replace('ChargingComplete', { chargePointId: undefined });
    }
  }, [stopRequested, hasEverActive, activeSession, navigation]);

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

  // 计算充电时长（必须在所有早期返回之前定义）
  const timeText = useMemo(() => {
    if (!activeSession?.start_time) return '';
    try {
      const startTime = new Date(activeSession.start_time).getTime();
      const now = Date.now();
      const minutes = Math.max(0, Math.round((now - startTime) / 1000 / 60));
      return `已充电 ${minutes} 分钟`;
    } catch {
      return '';
    }
  }, [activeSession?.start_time]);

  const canStop = !!activeSession && !stopRequested && chargerStatus === 'charging_self';

  const onStartCharging = () => {
    setUserConfirmedStart(true);
  };

  const onRetryStart = async () => {
    try {
      await dispatch(startCharging({ qrToken })).unwrap();
    } catch {
      // 错误已写入 slice.error
    }
  };

  const onStop = async () => {
    try {
      setStopRequested(true);
      await dispatch(stopChargingSession(qrToken)).unwrap();
    } catch {
      setStopRequested(false);
    }
  };

  const onRefreshStatus = async () => {
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
          dispatch(fetchActiveSession(qrToken));
        } else {
          setChargerStatus('charging_other');
        }
      } else {
        setChargerStatus('available');
      }
    } catch (e: any) {
      console.error('刷新状态失败:', e);
      let errorMsg = '刷新状态失败';
      if (e?.response?.status === 404) {
        errorMsg = '充电桩不存在或二维码无效';
      } else if (e?.response?.status === 400) {
        errorMsg = e?.response?.data?.detail || '二维码无效';
      } else if (e?.response?.data?.detail) {
        errorMsg = e.response.data.detail;
      } else if (e?.message) {
        errorMsg = e.message;
      }
      setStatusCheckError(errorMsg);
    }
  };

  // 渲染：检查状态中
  if (chargerStatus === 'checking') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
            <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>充电桩状态</Text>
          <View style={styles.headerRight} />
        </View>
        <View style={styles.centerContent}>
          <LoadingSpinner size="large" message="正在检查充电桩状态..." />
        </View>
      </SafeAreaView>
    );
  }

  // 渲染：离线状态
  if (chargerStatus === 'offline') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
            <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>充电桩离线</Text>
          <View style={styles.headerRight} />
        </View>
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Icon name="alert-circle" library="Ionicons" size={48} color={COLORS.ERROR} />
              <Text style={styles.statusTitle}>充电桩离线</Text>
              <Text style={styles.statusSubtitle}>无法开始充电</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>充电桩ID</Text>
              <Text style={styles.infoValue}>{statusCheckData?.charger_id || '—'}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>最后在线时间</Text>
              <Text style={styles.infoValue}>
                {statusCheckData?.last_seen
                  ? new Date(statusCheckData.last_seen).toLocaleString()
                  : '从未在线'}
              </Text>
            </View>

            {statusCheckError && (
              <View style={styles.errorNotice}>
                <Text style={styles.errorText}>{statusCheckError}</Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                title="刷新状态"
                onPress={onRefreshStatus}
                variant="outline"
                icon={{ name: 'refresh', library: 'Ionicons' }}
                style={styles.refreshButton}
              />
              <Button
                title="返回"
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
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
            <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>充电桩使用中</Text>
          <View style={styles.headerRight} />
        </View>
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Icon name="flash" library="Ionicons" size={48} color={COLORS.WARNING} />
              <Text style={styles.statusTitle}>充电桩正在使用中</Text>
              <Text style={styles.statusSubtitle}>其他用户正在使用此充电桩</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>充电桩ID</Text>
              <Text style={styles.infoValue}>{statusCheckData?.charger_id || '—'}</Text>
            </View>

            {statusCheckData?.charger_info?.site_name && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>站点名称</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_name}</Text>
              </View>
            )}

            {statusCheckData?.active_session?.start_time && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>充电开始时间</Text>
                <Text style={styles.infoValue}>
                  {new Date(statusCheckData.active_session.start_time).toLocaleString()}
                </Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                title="刷新状态"
                onPress={onRefreshStatus}
                variant="outline"
                icon={{ name: 'refresh', library: 'Ionicons' }}
                style={styles.refreshButton}
              />
              <Button
                title="返回"
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
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
            <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>准备充电</Text>
          <View style={styles.headerRight} />
        </View>
        <ScrollView style={styles.scrollContent}>
          <Card style={styles.card}>
            <View style={styles.statusHeader}>
              <Icon name="checkmark-circle" library="Ionicons" size={48} color={COLORS.SUCCESS} />
              <Text style={styles.statusTitle}>充电桩可用</Text>
              <Text style={styles.statusSubtitle}>确认信息后开始充电</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>充电桩ID</Text>
              <Text style={styles.infoValue}>{statusCheckData?.charger_id || '—'}</Text>
            </View>

            <View style={styles.infoSection}>
              <Text style={styles.infoLabel}>接口编号</Text>
              <Text style={styles.infoValue}>{statusCheckData?.connector_id || '—'}</Text>
            </View>

            {statusCheckData?.charger_info?.site_name && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>站点名称</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_name}</Text>
              </View>
            )}

            {statusCheckData?.charger_info?.site_address && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>站点地址</Text>
                <Text style={styles.infoValue}>{statusCheckData.charger_info.site_address}</Text>
              </View>
            )}

            {statusCheckData?.charger_info?.price_per_kwh && (
              <View style={styles.infoSection}>
                <Text style={styles.infoLabel}>价格</Text>
                <Text style={styles.infoValue}>
                  ${statusCheckData.charger_info.price_per_kwh.toFixed(2)} / kWh
                </Text>
              </View>
            )}

            <View style={styles.actionButtons}>
              <Button
                title="开始充电"
                onPress={onStartCharging}
                variant="primary"
                icon={{ name: 'flash', library: 'Ionicons' }}
                disabled={starting}
                loading={starting}
                style={styles.startButton}
              />
              <Button
                title="返回"
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
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>充电中</Text>
        <View style={styles.headerRight} />
      </View>

      <ScrollView style={styles.scrollContent} contentContainerStyle={styles.scrollContentContainer}>
        {/* 充电桩信息（简化） */}
        <View style={styles.chargerInfo}>
          <Text style={styles.chargerName}>
            {activeSession?.charge_point_id || statusCheckData?.charger_id || '—'}
          </Text>
          {activeSession?.start_time && (
            <Text style={styles.startTime}>开始时间：{startedText}</Text>
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
                    label: '功率',
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
              <Card style={styles.dataCard}>
                <View style={styles.dataGrid}>
                  <View style={styles.dataItem}>
                    <Text style={styles.dataLabel}>电压</Text>
                    <Text style={styles.dataValue}>
                      {typeof latestPoint.voltage_v === 'number' 
                        ? `${latestPoint.voltage_v.toFixed(0)} V` 
                        : '—'}
                    </Text>
                  </View>
                  <View style={styles.dataItem}>
                    <Text style={styles.dataLabel}>电流</Text>
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
                <Text style={styles.infoText}>等待实时数据...</Text>
              </Card>
            )}

            {/* 错误提示 */}
            {(error || meterError) && (
              <Card style={styles.errorCard}>
                <Text style={styles.errorText}>{error || meterError}</Text>
              </Card>
            )}

            {/* 控制请求状态（仅在启动/停止时显示） */}
            {(starting || stopping) && (
              <Card style={styles.statusCard}>
                <View style={styles.statusRow}>
                  <ActivityIndicator size="small" color={COLORS.PRIMARY} />
                  <Text style={styles.statusText}>
                    {starting ? '正在启动充电...' : stopping ? '正在停止充电...' : ''}
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
            title={stopping ? '正在停止...' : '结束充电'}
            onPress={onStop}
            variant="danger"
            disabled={stopping || !canStop}
            style={styles.stopButton}
            icon={{ name: 'stop-circle', library: 'Ionicons' }}
          />
        )}
        {!canStop && !stopRequested && (
          <Button
            title={starting ? '启动中...' : '重试启动'}
            onPress={onRetryStart}
            variant="primary"
            disabled={starting}
            loading={starting}
            style={styles.retryButton}
            icon={{ name: 'refresh', library: 'Ionicons' }}
          />
        )}
        {stopRequested && (
          <View style={styles.waitingContainer}>
            <ActivityIndicator size="small" color={COLORS.PRIMARY} />
            <Text style={styles.waitingText}>等待充电结束...</Text>
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
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  headerRight: { width: 44 },
  
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

  pointsBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: COLORS.BORDER, paddingTop: 10 },
  pointsTitle: { color: COLORS.TEXT_SECONDARY, fontWeight: '900', marginBottom: 6 },
  pointRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  pointText: { color: COLORS.TEXT_SECONDARY, fontSize: 12 },

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
  btn: { flex: 1, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY, marginRight: 10 },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
  danger: { backgroundColor: COLORS.ERROR },
  dangerText: { color: '#FFFFFF', fontWeight: '900' },
  disabled: { opacity: 0.5 },
});

export default ChargingProcessScreen;
