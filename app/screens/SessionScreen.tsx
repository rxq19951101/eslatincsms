/**
 * 本文件为 Session 页面：拉取充电桩状态，显示会话信息。
 * 用户点击"开始充电"时自动执行授权和启动充电。
 * 仅用于本地测试与演示。
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  Alert,
} from 'react-native';
import { API_ENDPOINTS } from '../config';

type Charger = {
  id: string;
  status: string;
  last_seen: string;
  session: {
    authorized: boolean;
    transaction_id: number | null;
    meter: number;
    order_id?: string;
  };
  connector_type?: string;  // 充电头类型: GBT, Type1, Type2, CCS1, CCS2
  charging_rate?: number;  // 充电速率 (kW)
  price_per_kwh?: number;  // 每度电价格 (COP/kWh)
};

type Order = {
  id: string;
  charger_id: string;
  user_id: string;
  id_tag: string;
  charging_rate: number;
  start_time: string;
  end_time?: string;
  duration_minutes?: number;
  energy_kwh?: number;
  status: string;
};

type SessionScreenProps = {
  route: any;
  navigation: any;
  user?: { username: string; idTag: string };
};

export default function SessionScreen({ route, navigation, user }: SessionScreenProps) {
  const { chargerId } = route.params;
  const [charger, setCharger] = useState<Charger | null>(null);
  const [loading, setLoading] = useState(true);
  const [charging, setCharging] = useState(false);
  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [elapsedTime, setElapsedTime] = useState<string>('00:00:00');
  const [chargedEnergy, setChargedEnergy] = useState<number>(0);
  const [spentAmount, setSpentAmount] = useState<number>(0);
  const [realTimeMeter, setRealTimeMeter] = useState<{
    meter_value_kwh: number;
    total_cost: number;
    duration_minutes: number | null;
    timestamp: string;
  } | null>(null);
  const [lastUpdateTime, setLastUpdateTime] = useState<string>('');

  useEffect(() => {
    fetchChargerStatus();
    // 每3秒刷新充电桩状态
    const interval = setInterval(fetchChargerStatus, 3000);
    return () => clearInterval(interval);
  }, [chargerId]);

  // 每60秒获取一次实时电量数据
  useEffect(() => {
    // 如果不在充电状态，清除实时数据
    if (!charger || charger.status !== 'Charging' || !charger.session.transaction_id) {
      setRealTimeMeter(null);
      return;
    }

    // 立即获取一次
    fetchRealTimeMeter();

    // 每60秒获取一次（60000毫秒 = 60秒）
    const interval = setInterval(() => {
      console.log('[SessionScreen] 定时器触发：获取实时电量数据');
      fetchRealTimeMeter();
    }, 60000);
    
    console.log('[SessionScreen] 已启动60秒定时器，用于获取实时电量数据');
    
    return () => {
      console.log('[SessionScreen] 清除60秒定时器');
      clearInterval(interval);
    };
  }, [charger?.status, charger?.session?.transaction_id, chargerId]);

  // 实时更新已充电时间和电量
  useEffect(() => {
    // 如果不在充电状态，清除显示
    if (!charger || charger.status !== 'Charging' || !charger.session.transaction_id) {
      setElapsedTime('00:00:00');
      setChargedEnergy(0);
      setSpentAmount(0);
      return;
    }

    // 如果有实时电量数据，优先使用实时数据
    if (realTimeMeter) {
      setChargedEnergy(realTimeMeter.meter_value_kwh);
      setSpentAmount(realTimeMeter.total_cost);
      
      // 使用实时数据的时长（如果有）
      if (realTimeMeter.duration_minutes !== null) {
        const totalSeconds = Math.floor(realTimeMeter.duration_minutes * 60);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        setElapsedTime(
          `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
        );
      }
    }

    // 如果有订单，使用订单的开始时间；否则使用充电桩的last_seen作为估计开始时间
    const getStartTime = () => {
      if (currentOrder && currentOrder.start_time) {
        return new Date(currentOrder.start_time);
      }
      // 如果没有订单，使用充电桩的last_seen作为估计（可能不够准确，但至少能显示）
      return new Date(charger.last_seen);
    };

    const updateElapsedTime = () => {
      try {
        // 如果已有实时数据，只更新时间显示
        if (realTimeMeter && realTimeMeter.duration_minutes !== null) {
          const totalSeconds = Math.floor(realTimeMeter.duration_minutes * 60);
          const hours = Math.floor(totalSeconds / 3600);
          const minutes = Math.floor((totalSeconds % 3600) / 60);
          const seconds = totalSeconds % 60;
          setElapsedTime(
            `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
          );
          return;
        }

        // 否则使用估算方式
        const startTime = getStartTime();
        const now = new Date();
        const diffMs = now.getTime() - startTime.getTime();
        
        if (diffMs < 0) {
          setElapsedTime('00:00:00');
          if (!realTimeMeter) {
            setChargedEnergy(0);
            setSpentAmount(0);
          }
          return;
        }
        
        // 计算小时、分钟、秒
        const hours = Math.floor(diffMs / (1000 * 60 * 60));
        const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);
        
        const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        setElapsedTime(timeStr);
        
        // 如果没有实时数据，使用估算方式
        if (!realTimeMeter) {
          // 计算已充电电量（kWh）= 充电速率（kW）× 时长（小时）
          const hoursDecimal = diffMs / (1000 * 60 * 60);
          const chargingRate = currentOrder?.charging_rate || charger.charging_rate || 7.0;
          const energyKwh = chargingRate * hoursDecimal;
          setChargedEnergy(Math.max(0, energyKwh));
          
          // 计算已花费金额（COP）= 电量（kWh）× 单价（从充电桩获取，默认2700 COP/kWh）
          const pricePerKwh = charger.price_per_kwh || 2700;
          const amount = energyKwh * pricePerKwh;
          setSpentAmount(Math.max(0, amount));
        }
      } catch (error) {
        console.error('[SessionScreen] 计算时间失败:', error);
      }
    };

    // 立即更新一次
    updateElapsedTime();
    
    // 每秒更新一次（仅更新时间显示）
    const interval = setInterval(updateElapsedTime, 1000);
    return () => clearInterval(interval);
  }, [charger, currentOrder, realTimeMeter]);

  const fetchChargerStatus = async () => {
    try {
      console.log('[SessionScreen] 正在请求充电桩状态:', API_ENDPOINTS.chargers, 'chargerId:', chargerId);
      const res = await fetch(API_ENDPOINTS.chargers, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const chargers: Charger[] = await res.json();
      console.log('[SessionScreen] 收到充电桩列表:', chargers.length, '个');
      const found = chargers.find((c) => c.id === chargerId);

      if (found) {
        setCharger(found);
        
        // 如果正在充电，获取当前订单信息
        if (found.status === 'Charging' && found.session.transaction_id) {
          fetchCurrentOrder(found.id, found.session.transaction_id);
        } else {
          setCurrentOrder(null);
        }
      } else {
        // Fallback: 使用假数据
        setCharger({
          id: chargerId,
          status: 'Available',
          last_seen: new Date().toISOString(),
          session: {
            authorized: false,
            transaction_id: null,
            meter: 0,
          },
        });
      }
    } catch (error: any) {
      console.error('[SessionScreen] 获取充电桩状态失败:', error);
      console.error('[SessionScreen] 错误详情:', {
        message: error?.message,
        name: error?.name,
        endpoint: API_ENDPOINTS.chargers,
      });
      // Fallback: 使用假数据
      if (!charger) {
        setCharger({
          id: chargerId,
          status: 'Unknown',
          last_seen: new Date().toISOString(),
          session: {
            authorized: false,
            transaction_id: null,
            meter: 0,
          },
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchCurrentOrder = async (chargePointId: string, transactionId: number) => {
    try {
      const url = `${API_ENDPOINTS.currentOrder}?chargePointId=${encodeURIComponent(chargePointId)}&transactionId=${transactionId}`;
      console.log('[SessionScreen] 正在请求当前订单:', url);
      
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (res.ok) {
        const order: Order | null = await res.json();
        if (order) {
          setCurrentOrder(order);
          console.log('[SessionScreen] 收到当前订单:', order.id, '开始时间:', order.start_time);
        } else {
          console.log('[SessionScreen] API返回null订单');
          setCurrentOrder(null);
        }
      } else {
        const errorText = await res.text();
        console.log('[SessionScreen] 未找到当前订单, 状态码:', res.status, '响应:', errorText);
        // 即使获取失败也不清除currentOrder，保持之前的值（如果有）
        // setCurrentOrder(null);
      }
    } catch (error) {
      console.error('[SessionScreen] 获取当前订单失败:', error);
      // 即使获取失败也不清除currentOrder，保持之前的值（如果有）
      // setCurrentOrder(null);
    }
  };

  const fetchRealTimeMeter = async () => {
    if (!charger || !charger.session.transaction_id) {
      console.log('[SessionScreen] 跳过获取实时电量：充电桩或事务ID不存在');
      return;
    }

    try {
      const url = `${API_ENDPOINTS.currentOrderMeter}?chargePointId=${encodeURIComponent(chargerId)}&transactionId=${charger.session.transaction_id}`;
      console.log('[SessionScreen] 正在请求实时电量数据:', url);
      
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (res.ok) {
        const meterData = await res.json();
        console.log('[SessionScreen] 收到实时电量数据:', {
          energy_kwh: meterData.meter_value_kwh,
          cost_cop: meterData.total_cost,
          duration_minutes: meterData.duration_minutes,
          timestamp: meterData.timestamp,
        });
        
        // 更新实时数据
        const updateTime = meterData.timestamp || new Date().toISOString();
        setRealTimeMeter({
          meter_value_kwh: meterData.meter_value_kwh || 0,
          total_cost: meterData.total_cost || 0,
          duration_minutes: meterData.duration_minutes || null,
          timestamp: updateTime,
        });
        setLastUpdateTime(new Date(updateTime).toLocaleTimeString());
      } else {
        const errorText = await res.text();
        console.warn('[SessionScreen] 获取实时电量数据失败, 状态码:', res.status, '响应:', errorText);
        // 不清除已有数据，保持显示最后一次成功的数据
      }
    } catch (error) {
      console.error('[SessionScreen] 获取实时电量数据失败:', error);
      // 不清除已有数据，保持显示最后一次成功的数据
    }
  };

  const handleStartCharging = async () => {
    if (!user) {
      Alert.alert('错误', '请先登录');
      return;
    }

    // 如果没有充电桩数据，使用默认值继续
    if (!charger) {
      console.log('[SessionScreen] 充电桩数据未找到，使用默认值继续');
    } else if (charger.status === 'Charging') {
      Alert.alert('提示', '充电桩正在充电中');
      return;
    } else if (charger.status === 'Faulted') {
      Alert.alert('提示', '充电桩当前故障，无法充电');
      return;
    }

    try {
      setCharging(true);

      // 自动调用远程启动充电（后台会自动执行 Authorize + StartTransaction）
      const res = await fetch(API_ENDPOINTS.remoteStart, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chargePointId: chargerId,
          idTag: user.idTag,
        }),
      });

      if (res.ok) {
        const responseData = await res.json();
        Alert.alert('成功', '充电已启动', [
          { text: '确定', onPress: () => {
            fetchChargerStatus();
            // 延迟一下再获取订单，确保订单已创建
            setTimeout(() => {
              if (charger) {
                fetchChargerStatus();
              }
            }, 500);
          }},
        ]);
      } else {
        const errorData = await res.json();
        Alert.alert('失败', errorData.detail || '启动充电失败');
      }
    } catch (error) {
      console.error('启动充电失败:', error);
      Alert.alert('错误', '网络连接失败，请检查网络');
    } finally {
      setCharging(false);
    }
  };

  const handleStopCharging = async () => {
    if (!charger) {
      Alert.alert('错误', '充电桩信息加载失败');
      return;
    }

    if (!charger.session.transaction_id) {
      Alert.alert('提示', '当前没有进行中的充电');
      return;
    }

    try {
      setCharging(true);

      const res = await fetch(API_ENDPOINTS.remoteStop, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chargePointId: chargerId,
        }),
      });

      if (res.ok) {
        Alert.alert('成功', '充电已停止', [
          { text: '确定', onPress: () => fetchChargerStatus() },
        ]);
      } else {
        const errorData = await res.json();
        Alert.alert('失败', errorData.detail || '停止充电失败');
      }
    } catch (error) {
      console.error('停止充电失败:', error);
      Alert.alert('错误', '网络连接失败，请检查网络');
    } finally {
      setCharging(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Available':
        return '#34c759';
      case 'Charging':
        return '#ff9500';
      case 'Faulted':
        return '#ff3b30';
      default:
        return '#8b5cf6';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'Available':
        return '可用';
      case 'Charging':
        return '充电中';
      case 'Faulted':
        return '故障';
      default:
        return status;
    }
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>充电会话</Text>
      <Text style={styles.chargerId}>{chargerId}</Text>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#007AFF" />
          <Text style={styles.loadingText}>加载中...</Text>
        </View>
      ) : charger ? (
        <View style={styles.statusContainer}>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>状态</Text>
            <Text style={[styles.statusValue, { color: getStatusColor(charger.status) }]}>
              {getStatusText(charger.status)}
            </Text>
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>最后更新</Text>
            <Text style={styles.statusValue}>
              {new Date(charger.last_seen).toLocaleString()}
            </Text>
          </View>
          {user && (
            <View style={styles.statusRow}>
              <Text style={styles.statusLabel}>充电ID</Text>
              <Text style={styles.statusValue}>{user.idTag}</Text>
            </View>
          )}
          {charger.session.transaction_id && (
            <View style={styles.statusRow}>
              <Text style={styles.statusLabel}>事务ID</Text>
              <Text style={styles.statusValue}>{charger.session.transaction_id}</Text>
            </View>
          )}
          {charger.charging_rate && (
            <View style={styles.statusRow}>
              <Text style={styles.statusLabel}>充电速率</Text>
              <Text style={styles.statusValue}>{charger.charging_rate} kW</Text>
            </View>
          )}
          {charger.status === 'Charging' && charger.session.transaction_id && (
            <>
              <View style={styles.statusRow}>
                <Text style={styles.statusLabel}>已充电时间</Text>
                <Text style={[styles.statusValue, styles.highlightValue]}>
                  {elapsedTime}
                </Text>
              </View>
              <View style={styles.statusRow}>
                <Text style={styles.statusLabel}>已消耗电量</Text>
                <View style={styles.valueContainer}>
                  <Text style={[styles.statusValue, styles.highlightValue]}>
                    {realTimeMeter ? realTimeMeter.meter_value_kwh.toFixed(3) : chargedEnergy.toFixed(2)} kWh
                  </Text>
                  {realTimeMeter && (
                    <Text style={styles.realTimeBadge}>实时</Text>
                  )}
                </View>
              </View>
              <View style={styles.statusRow}>
                <Text style={styles.statusLabel}>实时话费</Text>
                <View style={styles.valueContainer}>
                  <Text style={[styles.statusValue, styles.highlightValue]}>
                    {realTimeMeter ? realTimeMeter.total_cost.toFixed(2) : spentAmount.toFixed(0)} COP
                  </Text>
                  {realTimeMeter && (
                    <Text style={styles.realTimeBadge}>实时</Text>
                  )}
                </View>
              </View>
              {realTimeMeter && (
                <View style={styles.statusRow}>
                  <Text style={styles.statusLabel}>数据更新时间</Text>
                  <Text style={[styles.statusValue, { fontSize: 12, color: '#666' }]}>
                    {lastUpdateTime || new Date(realTimeMeter.timestamp).toLocaleTimeString()}
                  </Text>
                </View>
              )}
              {charger.status === 'Charging' && (
                <View style={styles.infoBox}>
                  <Text style={styles.infoText}>
                    💡 实时数据每60秒自动更新一次
                  </Text>
                </View>
              )}
            </>
          )}
          {charger.connector_type && (
            <View style={styles.statusRow}>
              <Text style={styles.statusLabel}>充电头类型</Text>
              <Text style={styles.statusValue}>{charger.connector_type}</Text>
            </View>
          )}
        </View>
      ) : (
        <Text style={styles.errorText}>未找到充电桩信息</Text>
      )}

      {/* 根据充电状态显示不同的按钮 */}
      {/* 如果正在充电，显示停止按钮 */}
      {charger && charger.status === 'Charging' && charger.session.transaction_id && (
        <TouchableOpacity
          style={[styles.buttonStop, charging && styles.buttonDisabled]}
          onPress={handleStopCharging}
          disabled={charging}
        >
          {charging ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>⏹ 停止充电</Text>
          )}
        </TouchableOpacity>
      )}

      {/* 如果不在充电状态，显示开始充电按钮 */}
      {/* 修复：如果状态是 Available，即使有旧的 transaction_id 也应该允许开始新的充电 */}
      {charger && charger.status !== 'Charging' && (
        <TouchableOpacity
          style={[styles.button, charging && styles.buttonDisabled]}
          onPress={handleStartCharging}
          disabled={charging}
        >
          {charging ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>⚡ 开始充电</Text>
          )}
        </TouchableOpacity>
      )}

      {/* 如果没有找到充电桩，也显示开始充电按钮（允许创建新充电桩） */}
      {!charger && !loading && (
        <TouchableOpacity
          style={[styles.button, charging && styles.buttonDisabled]}
          onPress={handleStartCharging}
          disabled={charging}
        >
          {charging ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>⚡ 开始充电</Text>
          )}
        </TouchableOpacity>
      )}

      <TouchableOpacity
        style={styles.buttonSecondary}
        onPress={() => navigation.goBack()}
      >
        <Text style={styles.buttonTextSecondary}>返回</Text>
      </TouchableOpacity>

      {!user && (
        <View style={styles.hintContainer}>
          <Text style={styles.hintText}>💡 提示：请先登录后再开始充电</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 28,
    fontWeight: '600',
    marginBottom: 8,
    marginTop: 16,
  },
  chargerId: {
    fontSize: 18,
    color: '#007AFF',
    marginBottom: 24,
    fontWeight: '600',
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  loadingText: {
    marginTop: 16,
    color: '#666',
  },
  statusContainer: {
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  statusLabel: {
    fontSize: 16,
    color: '#666',
    fontWeight: '500',
  },
  statusValue: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  highlightValue: {
    color: '#ff9500',
    fontSize: 18,
    fontWeight: '700',
  },
  valueContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  realTimeBadge: {
    fontSize: 10,
    color: '#34c759',
    backgroundColor: '#e8f5e9',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    fontWeight: '600',
  },
  button: {
    backgroundColor: '#34c759',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
    marginBottom: 12,
    shadowColor: '#34c759',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  buttonStop: {
    backgroundColor: '#ff3b30',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
    marginBottom: 12,
    shadowColor: '#ff3b30',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  buttonDisabled: {
    opacity: 0.6,
    shadowOpacity: 0.1,
  },
  buttonSecondary: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#007AFF',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
    marginBottom: 12,
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  buttonTextSecondary: {
    color: '#007AFF',
    fontSize: 18,
    fontWeight: '600',
  },
  errorText: {
    color: '#ff3b30',
    fontSize: 16,
    textAlign: 'center',
    marginTop: 32,
  },
  hintContainer: {
    backgroundColor: '#fff3cd',
    borderRadius: 8,
    padding: 16,
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#ffc107',
  },
  hintText: {
    fontSize: 14,
    color: '#856404',
    textAlign: 'center',
  },
  infoBox: {
    backgroundColor: '#e3f2fd',
    borderRadius: 8,
    padding: 12,
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#2196f3',
  },
  infoText: {
    fontSize: 12,
    color: '#1976d2',
    textAlign: 'center',
  },
});
