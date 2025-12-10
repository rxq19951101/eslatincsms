/**
 * 订单详情页面：显示已完成订单的详细信息
 * 包括充电时间、费用、电量等
 */

import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

type Order = {
  id: string;
  charger_id: string;
  user_id: string;
  id_tag: string;
  start_time: string;
  end_time?: string;
  duration_minutes?: number;
  energy_kwh?: number;
  cost_cop?: number;
  total_cost?: number;
  status: string;
  charging_rate?: number;
};

type OrderDetailScreenProps = {
  route: any;
  navigation: any;
};

export default function OrderDetailScreen({ route, navigation }: OrderDetailScreenProps) {
  const insets = useSafeAreaInsets();
  const { order } = route.params as { order: Order };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatDuration = (minutes?: number) => {
    if (!minutes) return '未知';
    const hours = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);
    if (hours > 0) {
      return `${hours}小时${mins}分钟`;
    }
    return `${mins}分钟`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return '#34c759';
      case 'ongoing':
        return '#ff9500';
      case 'cancelled':
        return '#ff3b30';
      default:
        return '#666';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed':
        return '已完成';
      case 'ongoing':
        return '进行中';
      case 'cancelled':
        return '已取消';
      default:
        return status;
    }
  };

  const totalCost = order.cost_cop || order.total_cost || 0;

  return (
    <SafeAreaView style={[styles.safeArea, { paddingTop: insets.top }]} edges={['top', 'left', 'right']}>
      <ScrollView
        style={styles.container}
        contentContainerStyle={{ paddingBottom: Math.max(insets.bottom, 24) }}
      >
        {/* 头部状态卡片 */}
        <View style={styles.headerCard}>
          <View style={styles.statusContainer}>
            <View
              style={[
                styles.statusBadge,
                { backgroundColor: getStatusColor(order.status) },
              ]}
            >
              <Text style={styles.statusText}>{getStatusText(order.status)}</Text>
            </View>
          </View>
          <Text style={styles.orderId}>订单号: {order.id}</Text>
          <Text style={styles.chargerId}>充电桩: {order.charger_id}</Text>
        </View>

        {/* 时间信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>时间信息</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>开始时间</Text>
            <Text style={styles.infoValue}>{formatDate(order.start_time)}</Text>
          </View>
          {order.end_time && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>结束时间</Text>
              <Text style={styles.infoValue}>{formatDate(order.end_time)}</Text>
            </View>
          )}
          {order.duration_minutes && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>充电时长</Text>
              <Text style={styles.infoValue}>{formatDuration(order.duration_minutes)}</Text>
            </View>
          )}
        </View>

        {/* 充电信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>充电信息</Text>
          {order.energy_kwh !== undefined && order.energy_kwh > 0 && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>充电电量</Text>
              <Text style={styles.infoValue}>{order.energy_kwh.toFixed(2)} kWh</Text>
            </View>
          )}
          {order.charging_rate && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>充电功率</Text>
              <Text style={styles.infoValue}>{order.charging_rate} kW</Text>
            </View>
          )}
        </View>

        {/* 费用信息 */}
        {totalCost > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>费用信息</Text>
            <View style={styles.costContainer}>
              <Text style={styles.costLabel}>总费用</Text>
              <Text style={styles.costValue}>{totalCost.toFixed(2)} COP</Text>
            </View>
            {order.energy_kwh && order.energy_kwh > 0 && (
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>单价</Text>
                <Text style={styles.infoValue}>
                  {(totalCost / order.energy_kwh).toFixed(2)} COP/kWh
                </Text>
              </View>
            )}
          </View>
        )}

        {/* 用户信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>用户信息</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>用户ID</Text>
            <Text style={styles.infoValue}>{order.user_id || order.id_tag}</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  headerCard: {
    backgroundColor: '#fff',
    padding: 20,
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  statusContainer: {
    alignItems: 'flex-start',
    marginBottom: 16,
  },
  statusBadge: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 16,
  },
  statusText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  orderId: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  chargerId: {
    fontSize: 14,
    color: '#007AFF',
  },
  section: {
    backgroundColor: '#fff',
    padding: 20,
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 15,
    color: '#666',
  },
  infoValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
  },
  costContainer: {
    backgroundColor: '#f8f9fa',
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    alignItems: 'center',
  },
  costLabel: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  costValue: {
    fontSize: 32,
    fontWeight: '700',
    color: '#007AFF',
  },
});
