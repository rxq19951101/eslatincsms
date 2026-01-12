/**
 * 充电站详情页（Phase 2.4）
 * 展示站点信息、状态、价格、连接器列表等
 */
 
import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StatusBar,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargerById } from '../../store/slices/chargerSlice';

type StationDetailRouteProp = RouteProp<RootStackParamList, 'StationDetail'>;
type StationDetailNavProp = StackNavigationProp<RootStackParamList, 'StationDetail'>;

const StationDetailScreen = () => {
  const dispatch = useAppDispatch();
  const navigation = useNavigation<StationDetailNavProp>();
  const route = useRoute<StationDetailRouteProp>();

  const { chargePointId } = route.params;
  const { selectedCharger, loading, error } = useAppSelector((state) => state.charger);

  const loadDetail = async () => {
    try {
      await dispatch(fetchChargerById(chargePointId)).unwrap();
    } catch {
      // 错误由 slice 写入 error，这里不额外弹窗，避免干扰
    }
  };

  useEffect(() => {
    loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chargePointId]);

  const charger = selectedCharger && selectedCharger.id === chargePointId ? selectedCharger : null;

  const isAvailable = (charger?.available_connectors || 0) > 0;
  const statusColor = !charger
    ? COLORS.TEXT_SECONDARY
    : charger.status === 'Offline'
    ? COLORS.ERROR
    : isAvailable
    ? COLORS.SUCCESS
    : COLORS.WARNING;

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>充电站详情</Text>
        <View style={styles.headerRight} />
      </View>

      <ScrollView
        style={styles.content}
        refreshControl={<RefreshControl refreshing={false} onRefresh={loadDetail} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Loading */}
        {loading && !charger && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={COLORS.PRIMARY} />
            <Text style={styles.loadingText}>加载中...</Text>
          </View>
        )}

        {/* Error */}
        {!!error && !charger && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorTitle}>加载失败</Text>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={loadDetail}>
              <Text style={styles.retryText}>重试</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Empty */}
        {!loading && !error && !charger && (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>🔎</Text>
            <Text style={styles.emptyTitle}>未找到充电站</Text>
            <Text style={styles.emptyText}>该充电站可能已被删除或暂无权限查看。</Text>
            <TouchableOpacity style={styles.retryButton} onPress={loadDetail}>
              <Text style={styles.retryText}>重新加载</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Detail */}
        {!!charger && (
          <>
            {/* 基本信息 */}
            <View style={styles.card}>
              <View style={styles.titleRow}>
                <View style={styles.titleLeft}>
                  <Text style={styles.title}>
                    {charger.site_name || `充电站 ${charger.id}`}
                  </Text>
                  <Text style={styles.subTitle}>{charger.site_address || '地址未知'}</Text>
                </View>
                <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
                  <Text style={styles.statusText}>{charger.status}</Text>
                </View>
              </View>

              <View style={styles.metricsRow}>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>可用接口</Text>
                  <Text style={styles.metricValue}>
                    {charger.available_connectors || 0}/{charger.total_connectors || 0}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>电价</Text>
                  <Text style={styles.metricValue}>
                    {typeof charger.price_per_kwh === 'number'
                      ? `$${charger.price_per_kwh.toFixed(2)}/kWh`
                      : '暂无'}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>评分</Text>
                  <Text style={styles.metricValue}>
                    {typeof (charger as any).rating === 'number' ? (charger as any).rating.toFixed(1) : '暂无'}
                  </Text>
                </View>
              </View>
            </View>

            {/* 连接器列表 */}
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>充电器/接口</Text>
              {Array.isArray((charger as any).connectors) && (charger as any).connectors.length > 0 ? (
                (charger as any).connectors.map((c: any) => {
                  const st = c.status || 'Unknown';
                  const stColor =
                    st === 'Available'
                      ? COLORS.SUCCESS
                      : st === 'Charging'
                      ? COLORS.WARNING
                      : st === 'Offline' || st === 'Faulted'
                      ? COLORS.ERROR
                      : COLORS.TEXT_SECONDARY;
                  return (
                    <View key={String(c.id)} style={styles.connectorRow}>
                      <View style={styles.connectorLeft}>
                        <Text style={styles.connectorName}>接口 #{c.connector_id ?? c.id}</Text>
                        <Text style={styles.connectorMeta}>
                          {c.connector_type ? `${c.connector_type} · ` : ''}
                          {typeof c.power_kw === 'number' ? `${c.power_kw} kW` : '功率未知'}
                        </Text>
                      </View>
                      <View style={[styles.connectorStatus, { backgroundColor: stColor }]}>
                        <Text style={styles.connectorStatusText}>{st}</Text>
                      </View>
                    </View>
                  );
                })
              ) : (
                <View style={styles.emptyBlock}>
                  <Text style={styles.emptyBlockText}>暂无接口数据</Text>
                </View>
              )}
            </View>
          </>
        )}
      </ScrollView>

      {/* Bottom actions */}
      <View style={styles.bottomBar}>
        <TouchableOpacity style={[styles.actionBtn, styles.secondaryBtn]} onPress={() => {}}>
          <Text style={styles.secondaryBtnText}>导航</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[
            styles.actionBtn,
            styles.primaryBtn,
            !isAvailable && styles.disabledBtn,
          ]}
          disabled={!isAvailable}
          onPress={() => {}}
        >
          <Text style={styles.primaryBtnText}>{isAvailable ? '开始充电' : '暂无可用接口'}</Text>
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
  backButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 22, color: COLORS.TEXT_PRIMARY },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '700', color: COLORS.TEXT_PRIMARY },
  headerRight: { width: 44 },

  content: { flex: 1, padding: 16 },

  loadingContainer: { paddingVertical: 40, alignItems: 'center' },
  loadingText: { marginTop: 10, color: COLORS.TEXT_SECONDARY },

  errorContainer: { paddingVertical: 24, alignItems: 'center' },
  errorTitle: { fontSize: 16, fontWeight: '700', color: COLORS.ERROR, marginBottom: 8 },
  errorText: { color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },

  emptyContainer: { paddingVertical: 32, alignItems: 'center' },
  emptyIcon: { fontSize: 56, marginBottom: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: COLORS.TEXT_PRIMARY, marginBottom: 6 },
  emptyText: { color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },

  retryButton: { paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10, backgroundColor: COLORS.PRIMARY },
  retryText: { color: '#FFFFFF', fontWeight: '700' },

  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  titleLeft: { flex: 1, paddingRight: 12 },
  title: { fontSize: 18, fontWeight: '800', color: COLORS.TEXT_PRIMARY, marginBottom: 6 },
  subTitle: { color: COLORS.TEXT_SECONDARY, lineHeight: 20 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12 },
  statusText: { color: '#FFFFFF', fontWeight: '700', fontSize: 12 },

  metricsRow: { flexDirection: 'row', marginTop: 14 },
  metricItem: { flex: 1 },
  metricLabel: { color: COLORS.TEXT_SECONDARY, fontSize: 12, marginBottom: 4 },
  metricValue: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },

  sectionTitle: { fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY, marginBottom: 10 },
  connectorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  connectorLeft: { flex: 1, paddingRight: 12 },
  connectorName: { fontWeight: '700', color: COLORS.TEXT_PRIMARY },
  connectorMeta: { marginTop: 4, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  connectorStatus: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12 },
  connectorStatusText: { color: '#FFFFFF', fontWeight: '700', fontSize: 12 },
  emptyBlock: { paddingVertical: 16, alignItems: 'center' },
  emptyBlockText: { color: COLORS.TEXT_SECONDARY },

  bottomBar: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  actionBtn: { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: 'center' },
  secondaryBtn: { backgroundColor: '#E5E7EB', marginRight: 10 },
  secondaryBtnText: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },
  primaryBtn: { backgroundColor: COLORS.PRIMARY },
  primaryBtnText: { color: '#FFFFFF', fontWeight: '800' },
  disabledBtn: { backgroundColor: COLORS.DISABLED },
});

export default StationDetailScreen;

