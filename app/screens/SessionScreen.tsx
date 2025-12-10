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
  Linking,
  Platform,
} from 'react-native';
import { API_ENDPOINTS } from '../config';

type Charger = {
  id: string;
  physical_status: string;  // 物理状态：只允许 OCPP 更新（Available / Charging / Faulted ...）
  operational_status: string;  // 运营状态：平台人工 & 运维系统控制（ENABLED / MAINTENANCE / DISABLED）
  is_available: boolean;  // 是否真正可用（计算字段）：physical_status = 'Available' AND operational_status = 'ENABLED'
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
  user?: { username: string; idTag: string; role?: string };
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
  const [lastTransactionId, setLastTransactionId] = useState<number | null>(null);
  const [hasShownNotFoundAlert, setHasShownNotFoundAlert] = useState(false);
  const [exportingLogs, setExportingLogs] = useState(false);

  useEffect(() => {
    fetchChargerStatus();
    // 每10秒刷新充电桩状态（减少服务器压力，充电会话页面需要更频繁的更新）
    const interval = setInterval(fetchChargerStatus, 10000);
    return () => clearInterval(interval);
  }, [chargerId]);

  // 每60秒获取一次实时电量数据
  useEffect(() => {
    // 如果不在充电状态，清除实时数据
    if (!charger || charger.physical_status !== 'Charging' || !charger.session.transaction_id) {
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
  }, [charger?.physical_status, charger?.session?.transaction_id, chargerId]);

  // 实时更新已充电时间和电量
  useEffect(() => {
    // 如果不在充电状态，清除显示
    if (!charger || charger.physical_status !== 'Charging' || !charger.session.transaction_id) {
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
        // 使用服务器返回的 is_available 字段判断是否可用
        // is_available = (physical_status = 'Available' AND operational_status = 'ENABLED')
        // 不再自己判断离线状态，完全由服务器和充电桩自身控制
        
        console.log(`[SessionScreen] 充电桩 ${chargerId} 状态: physical_status=${found.physical_status}, operational_status=${found.operational_status}, is_available=${found.is_available}`);
        
        // 更新充电桩状态
        setCharger(found);
        
        // 如果找到了充电桩，重置提示标志
        if (hasShownNotFoundAlert) {
          setHasShownNotFoundAlert(false);
        }
        
        // 如果正在充电，只在 transaction_id 变化时获取当前订单信息
        // 订单信息在充电过程中不会变化，不需要频繁请求
        const currentTransactionId = found.session.transaction_id;
        // 使用物理状态判断是否在充电
        if (found.physical_status === 'Charging' && currentTransactionId) {
          // 只在 transaction_id 变化时获取订单（新开始充电时）
          if (currentTransactionId !== lastTransactionId) {
            console.log('[SessionScreen] 检测到新的交易ID，获取订单信息:', currentTransactionId);
            fetchCurrentOrder(found.id, currentTransactionId);
            setLastTransactionId(currentTransactionId);
          }
        } else {
          // 如果不在充电状态，清除订单和交易ID记录
          if (currentOrder) {
            setCurrentOrder(null);
          }
          if (lastTransactionId !== null) {
            setLastTransactionId(null);
          }
        }
      } else {
        // 充电桩不在列表中，可能是离线或不存在
        console.warn('[SessionScreen] 充电桩未找到，可能离线或不存在:', chargerId);
        
        // 只在首次检测到不存在时显示一次提示
        if (!hasShownNotFoundAlert && !charger) {
          setHasShownNotFoundAlert(true);
          // 延迟显示，避免在页面加载时立即弹出
          setTimeout(() => {
            Alert.alert(
              '充电桩未找到',
              `该充电桩（${chargerId}）不在系统中。\n\n可能原因：\n• 该充电桩不属于我公司\n• 充电桩尚未注册到系统\n• 充电桩当前离线`,
              [{ text: '确定' }]
            );
          }, 500);
        }
        
        setCharger({
          id: chargerId,
          physical_status: 'Unavailable',
          operational_status: 'ENABLED',
          is_available: false,
          last_seen: '', // 离线充电桩没有最后更新时间
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
      // 网络错误或其他错误，如果还没有充电桩数据，设置为离线状态
      if (!charger) {
        console.warn('[SessionScreen] 获取充电桩状态失败，设置为离线状态');
        setCharger({
          id: chargerId,
          physical_status: 'Unavailable',
          operational_status: 'ENABLED',
          is_available: false,
          last_seen: '',
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
    } else if (charger.physical_status === 'Charging') {
      Alert.alert('提示', '充电桩正在充电中');
      return;
    } else if (charger.physical_status === 'Faulted') {
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

  const fetchOrderById = async (orderId: string): Promise<Order | null> => {
    try {
      // 获取当前用户的订单列表
      if (!user) {
        console.warn('[SessionScreen] 用户未登录，无法获取订单');
        return null;
      }

      const url = `${API_ENDPOINTS.orders}?userId=${encodeURIComponent(user.idTag)}`;
      console.log('[SessionScreen] 正在获取订单列表以查找订单:', orderId);
      
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) {
        console.warn('[SessionScreen] 获取订单列表失败:', res.status);
        return null;
      }

      const orders: Order[] = await res.json();
      const order = orders.find((o) => o.id === orderId);
      
      if (order) {
        console.log('[SessionScreen] 找到订单:', orderId);
        return order;
      } else {
        console.warn('[SessionScreen] 未找到订单:', orderId);
        return null;
      }
    } catch (error) {
      console.error('[SessionScreen] 获取订单失败:', error);
      return null;
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

    // 保存当前的订单ID，用于停止后跳转
    const currentOrderId = currentOrder?.id || charger.session.order_id;

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
        const responseData = await res.json();
        console.log('[SessionScreen] 停止充电响应:', responseData);
        
        // 从响应中获取订单ID（优先使用响应中的，然后是保存的）
        const orderId = responseData.details?.orderId || currentOrderId;
        
        // 更新充电桩状态
        fetchChargerStatus();
        
        if (orderId) {
          // 等待一小段时间，确保订单已更新为完成状态
          await new Promise(resolve => setTimeout(resolve, 1500));
          
          // 获取订单详情（重试几次，因为订单可能还在更新中）
          let order: Order | null = null;
          for (let i = 0; i < 3; i++) {
            order = await fetchOrderById(orderId);
            // 如果订单存在且已完成，或者订单存在（可能状态还在更新中），都可以显示
            if (order) {
              console.log('[SessionScreen] 找到订单，状态:', order.status);
              break;
            }
            if (i < 2) {
              console.log(`[SessionScreen] 订单未找到，重试 ${i + 1}/2...`);
              await new Promise(resolve => setTimeout(resolve, 1000));
            }
          }
          
          if (order) {
            // 直接导航到订单详情页面
            console.log('[SessionScreen] 导航到订单详情页面:', orderId);
            navigation.navigate('OrderDetail', { order });
          } else {
            // 如果找不到订单，显示成功提示
            console.warn('[SessionScreen] 未找到订单，显示成功提示');
            Alert.alert('成功', '充电已停止', [
              { text: '确定' },
            ]);
          }
        } else {
          // 没有订单ID，只显示成功提示
          Alert.alert('成功', '充电已停止', [
            { text: '确定' },
          ]);
        }
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
      case 'Maintenance':
        return '#ff9500'; // 维修中，使用橙色
      case 'Unavailable':
        return '#8e8e93';
      case 'Offline':
        return '#8e8e93';
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
      case 'Maintenance':
        return '维修中';
      case 'Unavailable':
        return '离线';
      case 'Offline':
        return '离线';
      default:
        return status;
    }
  };

  const handleExportLogs = async () => {
    if (!charger) {
      Alert.alert('错误', '充电桩信息加载失败');
      return;
    }

    try {
      setExportingLogs(true);

      const res = await fetch(API_ENDPOINTS.exportLogs, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chargePointId: chargerId,
          location: '',  // 使用默认位置
          userRole: user?.role || 'user',  // 传递用户角色
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: '导出失败' }));
        throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
      }

      // 获取响应内容
      const text = await res.text();
      
      // 尝试使用expo-file-system和expo-sharing保存和分享文件
      // 如果库不存在，会捕获错误并显示成功消息
      try {
        // 动态导入，如果库不存在会抛出错误
        // 使用类型断言来避免TypeScript错误
        const FileSystemModule = await import('expo-file-system');
        let SharingModule: any = null;
        try {
          // 使用eval来避免TypeScript静态检查
          // eslint-disable-next-line no-eval
          SharingModule = await eval('import("expo-sharing")');
        } catch {
          // expo-sharing可能未安装，继续使用FileSystem
        }
        
        const FileSystem = FileSystemModule.default;
        const Sharing = SharingModule?.default;
        
        // 使用类型断言来访问可能存在的属性
        const docDir = (FileSystem as any).documentDirectory;
        if (docDir) {
          const filename = `charger_${chargerId}_logs_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
          const fileUri = `${docDir}${filename}`;
          
          // 写入文件
          await (FileSystem as any).writeAsStringAsync(fileUri, text);
          
          // 分享文件（如果Sharing可用）
          if (Sharing && await (Sharing as any).isAvailableAsync()) {
            await (Sharing as any).shareAsync(fileUri, {
              mimeType: 'application/json',
              dialogTitle: '导出充电桩日志',
            });
            Alert.alert('成功', '日志已导出，请选择保存位置');
          } else {
            Alert.alert('成功', `日志已保存到: ${filename}`);
          }
          return;
        }
      } catch (fileError: any) {
        // 如果文件系统库不可用，继续执行下面的代码
        console.log('文件系统库不可用，使用备用方案:', fileError.message);
      }
      
      // 备用方案：显示成功消息，并允许查看日志内容
      console.log('日志内容:', text);
      Alert.alert(
        '成功', 
        '日志导出请求已发送。\n\n提示：如需保存文件，请安装expo-file-system和expo-sharing库。',
        [
          { text: '确定' },
          { 
            text: '查看内容', 
            onPress: () => {
              // 在开发环境中，可以显示日志内容
              if (__DEV__) {
                Alert.alert('日志内容', text.substring(0, 500) + (text.length > 500 ? '...' : ''));
              }
            }
          }
        ]
      );
    } catch (error: any) {
      console.error('导出日志失败:', error);
      Alert.alert('失败', error.message || '导出日志失败，请检查网络连接');
    } finally {
      setExportingLogs(false);
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
            <Text style={[styles.statusValue, { color: getStatusColor(charger.physical_status) }]}>
              {getStatusText(charger.physical_status)}
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
          {charger.physical_status === 'Charging' && charger.session.transaction_id && (
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
              {charger.physical_status === 'Charging' && (
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
      {charger && charger.physical_status === 'Charging' && charger.session.transaction_id && (
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

      {/* 如果不在充电状态且状态为可用，显示开始充电按钮 */}
      {/* 只有状态为 Available 时才允许开始充电（维修中、离线、故障等状态禁止使用） */}
      {charger && charger.physical_status === 'Available' && charger.is_available && (
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

      {/* 如果充电桩维修中，显示提示信息 */}
      {charger && charger.operational_status === 'MAINTENANCE' && (
        <View style={styles.maintenanceContainer}>
          <Text style={styles.maintenanceIcon}>🔧</Text>
          <Text style={styles.maintenanceTitle}>充电桩维修中</Text>
          <Text style={styles.maintenanceText}>
            该充电桩当前正在维修，暂时无法使用。{'\n'}
            维修完成后将恢复正常使用。
          </Text>
        </View>
      )}

      {/* 如果充电桩离线或不可用，显示提示信息 */}
      {charger && !charger.is_available && charger.physical_status !== 'Charging' && charger.physical_status !== 'Faulted' && (
        <View style={styles.offlineContainer}>
          <Text style={styles.offlineIcon}>📴</Text>
          <Text style={styles.offlineTitle}>充电桩离线</Text>
          <Text style={styles.offlineText}>
            该充电桩当前不在线，无法开始充电。{'\n'}
            请检查充电桩是否已连接网络，或稍后再试。
          </Text>
        </View>
      )}

      {/* 日志导出按钮 - 仅管理员可见 */}
      {charger && user && user.role === 'admin' && (
        <TouchableOpacity
          style={[styles.buttonSecondary, exportingLogs && styles.buttonDisabled]}
          onPress={handleExportLogs}
          disabled={exportingLogs}
        >
          {exportingLogs ? (
            <ActivityIndicator color="#007AFF" />
          ) : (
            <Text style={styles.buttonTextSecondary}>📥 导出日志</Text>
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
  offlineContainer: {
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  offlineIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  offlineTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    marginBottom: 12,
  },
  offlineText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 20,
  },
  maintenanceContainer: {
    backgroundColor: '#fff3cd',
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ffc107',
  },
  maintenanceIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  maintenanceTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#856404',
    marginBottom: 12,
  },
  maintenanceText: {
    fontSize: 14,
    color: '#856404',
    textAlign: 'center',
    lineHeight: 20,
  },
});
