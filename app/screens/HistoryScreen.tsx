/**
 * 本文件为充电历史记录页面：显示用户的充电历史。
 * 仅用于本地测试与演示。
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { API_ENDPOINTS } from '../config';

type ChargeSession = {
  id: string;
  chargerId: string;
  startTime: string;
  endTime?: string;
  duration?: number;
  energyKwh: number;
  cost?: number;
  status: 'completed' | 'ongoing' | 'cancelled';
};

type HistoryScreenProps = {
  navigation: any;
};

export default function HistoryScreen({ navigation }: HistoryScreenProps) {
  const insets = useSafeAreaInsets();
  const [sessions, setSessions] = useState<ChargeSession[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      // 获取当前用户信息
      const userStr = await AsyncStorage.getItem('current_user');
      if (!userStr) {
        console.log('[HistoryScreen] 未登录，无法加载订单');
        setSessions([]);
        return;
      }
      
      const user = JSON.parse(userStr);
      const userId = user.idTag;
      
      // 从API获取订单
      const url = `${API_ENDPOINTS.orders}?userId=${encodeURIComponent(userId)}`;
      console.log('[HistoryScreen] 正在请求订单列表:', url);
      
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const orders: any[] = await res.json();
      console.log('[HistoryScreen] 收到订单数据:', orders.length, '个');
      
      // 将订单数据转换为ChargeSession格式
      const sessions: ChargeSession[] = orders.map((order) => {
        const status = order.status === 'completed' ? 'completed' :
                      order.status === 'ongoing' ? 'ongoing' : 'cancelled';
        
        return {
          id: order.id,
          chargerId: order.charger_id,
          startTime: order.start_time,
          endTime: order.end_time || undefined,
          duration: order.duration_minutes || undefined,
          energyKwh: order.energy_kwh || 0,
          cost: undefined, // 费用计算可以后续添加
          status: status,
        };
      });
      
      setSessions(sessions);
    } catch (error: any) {
      console.error('[HistoryScreen] 加载历史记录失败:', error);
      // 如果API失败，尝试从本地存储加载（作为fallback）
      try {
        const stored = await AsyncStorage.getItem('charge_history');
        if (stored) {
          setSessions(JSON.parse(stored));
        }
      } catch (e) {
        console.error('[HistoryScreen] 加载本地历史记录也失败:', e);
      }
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadHistory();
    setRefreshing(false);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
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

  return (
    <SafeAreaView style={[styles.safeArea, { paddingTop: insets.top }]} edges={['top', 'left', 'right']}>
      <ScrollView
        style={styles.container}
        contentContainerStyle={{ paddingBottom: Math.max(insets.bottom, 24) }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
      <View style={styles.header}>
        <Text style={styles.headerTitle}>充电历史</Text>
        <Text style={styles.headerSubtitle}>共 {sessions.length} 条记录</Text>
      </View>

      {sessions.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyIcon}>📋</Text>
          <Text style={styles.emptyText}>暂无充电记录</Text>
          <TouchableOpacity
            style={styles.startButton}
            onPress={() => navigation.navigate('Map')}
          >
            <Text style={styles.startButtonText}>去充电</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.listContainer}>
          {sessions.map((session) => (
            <View key={session.id} style={styles.sessionCard}>
              <View style={styles.sessionHeader}>
                <View style={styles.sessionInfo}>
                  <Text style={styles.chargerId}>{session.chargerId}</Text>
                  <Text style={styles.timeText}>{formatDate(session.startTime)}</Text>
                </View>
                <View
                  style={[
                    styles.statusBadge,
                    { backgroundColor: getStatusColor(session.status) },
                  ]}
                >
                  <Text style={styles.statusText}>{getStatusText(session.status)}</Text>
                </View>
              </View>

              <View style={styles.sessionDetails}>
                {session.duration && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>时长</Text>
                    <Text style={styles.detailValue}>{session.duration} 分钟</Text>
                  </View>
                )}
                {session.energyKwh > 0 && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>电量</Text>
                    <Text style={styles.detailValue}>{session.energyKwh} kWh</Text>
                  </View>
                )}
                {session.cost && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>费用</Text>
                    <Text style={styles.detailValue}>¥{session.cost.toFixed(2)}</Text>
                  </View>
                )}
              </View>
            </View>
          ))}
        </View>
      )}
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
  header: {
    backgroundColor: '#fff',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#333',
    marginBottom: 4,
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#666',
  },
  listContainer: {
    padding: 16,
  },
  sessionCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  sessionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  sessionInfo: {
    flex: 1,
  },
  chargerId: {
    fontSize: 18,
    fontWeight: '600',
    color: '#007AFF',
    marginBottom: 4,
  },
  timeText: {
    fontSize: 14,
    color: '#666',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  statusText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  sessionDetails: {
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
    paddingTop: 12,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  detailLabel: {
    fontSize: 14,
    color: '#666',
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 80,
  },
  emptyIcon: {
    fontSize: 80,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 18,
    color: '#666',
    marginBottom: 24,
  },
  startButton: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    paddingHorizontal: 32,
    paddingVertical: 12,
  },
  startButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

