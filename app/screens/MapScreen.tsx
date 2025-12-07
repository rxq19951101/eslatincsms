/**
 * 本文件为地图页面：显示充电桩位置和搜索功能。
 * 使用 react-native-maps 和 expo-location 显示真实地图和位置。
 * 仅用于本地测试与演示。
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import MapView, { Marker, PROVIDER_GOOGLE } from 'react-native-maps';
import * as Location from 'expo-location';
import { API_ENDPOINTS } from '../config';

type Charger = {
  id: string;
  name: string;
  address: string;
  status: string;
  latitude?: number;
  longitude?: number;
  connector_type?: string;  // 充电头类型: GBT, Type1, Type2, CCS1, CCS2
  charging_rate?: number;  // 充电速率 (kW)
};

type MapScreenProps = {
  navigation: any;
};

export default function MapScreen({ navigation }: MapScreenProps) {
  const insets = useSafeAreaInsets();
  const [searchQuery, setSearchQuery] = useState('');
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [locationPermission, setLocationPermission] = useState(false);
  const [chargers, setChargers] = useState<Charger[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    requestLocationPermission();
    fetchChargers();
    // 每3秒更新一次充电桩数据
    const interval = setInterval(fetchChargers, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchChargers = async () => {
    try {
      setLoading(true);
      console.log('[MapScreen] 正在请求充电桩列表:', API_ENDPOINTS.chargers);
      const res = await fetch(API_ENDPOINTS.chargers, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const data: any[] = await res.json();
      console.log('[MapScreen] 收到充电桩数据:', data.length, '个');
      
      const chargersWithLocation = data.map(c => ({
        id: c.id,
        name: c.id, // 使用ID作为名称
        address: c.location?.address || '',
        status: c.status || 'Unknown',
        latitude: c.location?.latitude,
        longitude: c.location?.longitude,
        connector_type: c.connector_type,
        charging_rate: c.charging_rate,
      })).filter(c => c.latitude && c.longitude) as Charger[];
      
      console.log('[MapScreen] 过滤后有位置的充电桩:', chargersWithLocation.length, '个');
      setChargers(chargersWithLocation);
    } catch (error: any) {
      console.error('[MapScreen] 获取充电桩失败:', error);
      console.error('[MapScreen] 错误详情:', {
        message: error?.message,
        name: error?.name,
        stack: error?.stack,
        endpoint: API_ENDPOINTS.chargers,
      });
      // 显示用户友好的错误提示
      if (error?.message?.includes('Network request failed') || error?.message?.includes('timed out')) {
        Alert.alert(
          '网络连接失败',
          `无法连接到服务器 ${API_ENDPOINTS.chargers}\n\n请检查：\n1. CSMS 服务是否运行（端口 9000）\n2. 设备与服务器是否在同一网络\n3. IP 地址配置是否正确`,
          [{ text: '确定' }]
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const requestLocationPermission = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        setLocationPermission(true);
        const location = await Location.getCurrentPositionAsync({});
        setLocation(location);
      } else {
        setLocationPermission(false);
        Alert.alert('定位权限', '需要定位权限以显示您的位置');
      }
    } catch (error) {
      console.error('定位错误:', error);
      setLocationPermission(false);
    }
  };

  const handleGetLocation = async () => {
    if (!locationPermission) {
      await requestLocationPermission();
      return;
    }

    try {
      const location = await Location.getCurrentPositionAsync({});
      setLocation(location);
    } catch (error) {
      console.error('获取位置失败:', error);
      Alert.alert('错误', '无法获取当前位置');
    }
  };

  return (
    <SafeAreaView style={[styles.safeArea, { paddingTop: insets.top }]}
      edges={['top', 'left', 'right']}
    >
      <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="Q Buscar una dirección"
          value={searchQuery}
          onChangeText={setSearchQuery}
          autoCapitalize="none"
        />
        <TouchableOpacity style={styles.locationButton} onPress={handleGetLocation}>
          <Text style={styles.locationButtonText}>📍</Text>
        </TouchableOpacity>
      </View>

      {/* 筛选栏 */}
      <View style={styles.filterContainer}>
        <TouchableOpacity style={styles.filterButton}>
          <Text style={styles.filterButtonText}>🔧 Conector</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.filterButton}>
          <Text style={styles.filterButtonText}>⚡ Disponibilidad</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.filterButton}>
          <Text style={styles.filterButtonText}>🔋 Potencia</Text>
        </TouchableOpacity>
      </View>

      {/* 地图视图 */}
      <View style={styles.mapContainer}>
        {(location || chargers.length > 0) ? (
          <MapView
            style={styles.map}
            provider={Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined}
            initialRegion={location ? {
              latitude: location.coords.latitude,
              longitude: location.coords.longitude,
              latitudeDelta: 0.1,
              longitudeDelta: 0.1,
            } : {
              latitude: 4.6110,
              longitude: -74.0708,
              latitudeDelta: 0.1,
              longitudeDelta: 0.1,
            }}
            showsUserLocation={!!location}
            showsMyLocationButton={false}
          >
            {chargers.map((charger) => {
              if (charger.latitude && charger.longitude) {
                return (
                  <Marker
                    key={charger.id}
                    coordinate={{
                      latitude: charger.latitude,
                      longitude: charger.longitude,
                    }}
                    title={charger.name}
                    description={charger.address}
                    pinColor={
                      charger.status === 'Available' ? '#34c759' :
                      charger.status === 'Charging' ? '#ff9500' : '#ff3b30'
                    }
                    onPress={() => navigation.navigate('Session', { chargerId: charger.id })}
                  />
                );
              }
              return null;
            })}
          </MapView>
        ) : (
          <View style={styles.mapPlaceholderContainer}>
            <Text style={styles.mapPlaceholder}>🗺️ 地图加载中...</Text>
            <Text style={styles.mapHint}>
              {!location ? '正在请求定位权限，请允许访问您的位置' : '暂无充电桩位置数据'}
            </Text>
          </View>
        )}
      </View>

      {/* 底部充电桩列表 */}
      <ScrollView
        horizontal
        style={[styles.bottomList, { paddingBottom: Math.max(insets.bottom, 20) + 8 }]}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: Math.max(insets.bottom, 20), paddingHorizontal: 8 }}
      >
        {chargers.map((charger) => (
          <TouchableOpacity
            key={charger.id}
            style={styles.chargerCard}
            onPress={() => navigation.navigate('Session', { chargerId: charger.id })}
          >
            <View style={styles.chargerHeader}>
              <Text style={styles.chargerName}>{charger.name}</Text>
              <View style={[
                styles.statusBadge,
                charger.status === 'Available' && styles.statusAvailable,
                charger.status === 'Charging' && styles.statusCharging,
                charger.status === 'Faulted' && styles.statusFaulted,
              ]}>
                <Text style={styles.statusText}>
                  {charger.status === 'Available' ? '可用' :
                   charger.status === 'Charging' ? '充电中' : '故障'}
                </Text>
              </View>
            </View>
            <Text style={styles.chargerAddress}>{charger.address}</Text>
            <Text style={styles.chargerId}>ID: {charger.id}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      </View>
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
  searchContainer: {
    flexDirection: 'row',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  searchInput: {
    flex: 1,
    height: 44,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 16,
    backgroundColor: '#f9f9f9',
  },
  locationButton: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 8,
    backgroundColor: '#007AFF',
    borderRadius: 8,
  },
  locationButtonText: {
    fontSize: 20,
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  filterButton: {
    backgroundColor: '#f9f9f9',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginRight: 8,
  },
  filterButtonText: {
    fontSize: 14,
    color: '#333',
  },
  mapContainer: {
    flex: 1,
  },
  map: {
    width: '100%',
    height: '100%',
  },
  mapPlaceholderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#e8f4f8',
  },
  mapPlaceholder: {
    fontSize: 48,
    textAlign: 'center',
    marginBottom: 16,
  },
  mapHint: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    paddingHorizontal: 32,
  },
  bottomList: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    maxHeight: 200,
    backgroundColor: 'transparent',
  },
  chargerCard: {
    width: 280,
    backgroundColor: '#fff',
    marginHorizontal: 8,
    padding: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  chargerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  chargerName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusAvailable: {
    backgroundColor: '#34c759',
  },
  statusCharging: {
    backgroundColor: '#ff9500',
  },
  statusFaulted: {
    backgroundColor: '#ff3b30',
  },
  statusText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  chargerAddress: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  chargerId: {
    fontSize: 12,
    color: '#999',
  },
});

