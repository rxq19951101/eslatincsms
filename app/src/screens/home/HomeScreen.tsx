/**
 * 主页 - 充电站列表和地图视图
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  FlatList,
  StatusBar,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { COLORS, MAP_CONFIG } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargers, fetchNearbyChargers } from '../../store/slices/chargerSlice';
import { Charger } from '../../api/chargers';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
// 地图组件（仅移动端）
import { Platform } from 'react-native';
let CustomMapView: any = null;
let ClusteredMarkers: any = null;

if (Platform.OS !== 'web') {
  try {
    CustomMapView = require('../../components/MapView').default;
    const ChargerMarkerModule = require('../../components/ChargerMarker');
    ClusteredMarkers = ChargerMarkerModule.ClusteredMarkers;
  } catch (e) {
    console.warn('Failed to load map components:', e);
  }
}

const HomeScreen = () => {
  const dispatch = useAppDispatch();
  const { chargers, loading, error } = useAppSelector((state) => state.charger);
  const navigation = useNavigation<StackNavigationProp<RootStackParamList>>();
  
  const [viewMode, setViewMode] = useState<'list' | 'map'>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [userLocation, setUserLocation] = useState<[number, number] | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // 获取用户位置并加载附近充电站
  useEffect(() => {
    loadChargers();
  }, []);

  const loadChargers = async () => {
    try {
      // 尝试获取用户当前位置
      const { status } = await Location.getForegroundPermissionsAsync();
      
      if (status === 'granted') {
        const location = await Location.getCurrentPositionAsync({});
        const coords: [number, number] = [
          location.coords.longitude,
          location.coords.latitude,
        ];
        setUserLocation(coords);
        
        // 获取附近的充电站
        dispatch(
          fetchNearbyChargers({
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
            radius: MAP_CONFIG.SEARCH_RADIUS,
          })
        );
      } else {
        // 没有位置权限，获取所有充电站
        dispatch(fetchChargers({ filter_type: 'configured' }));
      }
    } catch (err) {
      console.error('Failed to load chargers:', err);
      // 出错时也获取所有充电站
      dispatch(fetchChargers({ filter_type: 'configured' }));
    }
  };

  const handleRefresh = () => {
    loadChargers();
  };

  const handleMarkerPress = (charger: Charger) => {
    // 进入详情页（Phase 2.4）
    navigation.navigate('StationDetail', { chargePointId: charger.id });
  };

  const renderStationCard = ({ item }: { item: Charger }) => {
    const available = item.available_connectors || 0;
    const total = item.total_connectors || 0;
    const isAvailable = available > 0;

    return (
      <TouchableOpacity
        style={styles.stationCard}
        activeOpacity={0.7}
        onPress={() => handleMarkerPress(item)}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.stationName}>
            {item.site_name || `充电站 ${item.id}`}
          </Text>
          <View style={styles.statusDot}>
            <View
              style={[
                styles.dot,
                {
                  backgroundColor: isAvailable
                    ? COLORS.SUCCESS
                    : item.status === 'Offline'
                    ? COLORS.ERROR
                    : COLORS.WARNING,
                },
              ]}
            />
          </View>
        </View>

        <Text style={styles.stationAddress}>
          {item.site_address || '地址未知'}
        </Text>

        <View style={styles.cardFooter}>
          <View style={styles.infoItem}>
            <Text style={styles.infoIcon}>⚡</Text>
            <Text
              style={[styles.infoText, !isAvailable && styles.unavailableText]}
            >
              {available}/{total} 可用
            </Text>
          </View>

          {item.price_per_kwh && (
            <View style={styles.infoItem}>
              <Text style={styles.infoIcon}>💵</Text>
              <Text style={styles.infoText}>
                ${item.price_per_kwh.toFixed(2)}/kWh
              </Text>
            </View>
          )}

          <View style={styles.infoItem}>
            <Text style={styles.infoIcon}>📡</Text>
            <Text style={styles.infoText}>{item.status}</Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  // 筛选充电站（根据搜索词）
  const filteredChargers = chargers.filter((charger) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      charger.id.toLowerCase().includes(query) ||
      charger.site_name?.toLowerCase().includes(query) ||
      charger.site_address?.toLowerCase().includes(query) ||
      charger.vendor?.toLowerCase().includes(query)
    );
  });

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>充电站</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.refreshButton} onPress={handleRefresh}>
            <Text style={styles.refreshIcon}>🔄</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.filterButton}>
            <Text style={styles.filterIcon}>⚙️</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <Text style={styles.searchIcon}>🔍</Text>
        <TextInput
          style={styles.searchInput}
          placeholder="搜索充电站..."
          placeholderTextColor={COLORS.TEXT_SECONDARY}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {/* 加载和错误状态 */}
      {loading && viewMode === 'list' && (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.loadingText}>加载中...</Text>
        </View>
      )}

      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>❌ {error}</Text>
          <TouchableOpacity style={styles.retryButton} onPress={handleRefresh}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* View Mode Toggle */}
      {!loading && !error && (
        <View style={styles.viewToggle}>
          <TouchableOpacity
            style={[
              styles.toggleButton,
              viewMode === 'list' && styles.toggleButtonActive,
            ]}
            onPress={() => setViewMode('list')}
          >
            <Text
              style={[
                styles.toggleText,
                viewMode === 'list' && styles.toggleTextActive,
              ]}
            >
              列表 ({filteredChargers.length})
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.toggleButton,
              viewMode === 'map' && styles.toggleButtonActive,
            ]}
            onPress={() => setViewMode('map')}
          >
            <Text
              style={[
                styles.toggleText,
                viewMode === 'map' && styles.toggleTextActive,
              ]}
            >
              地图
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Content */}
      {!loading && !error && (
        <>
          {viewMode === 'list' ? (
            <FlatList
              data={filteredChargers}
              renderItem={renderStationCard}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              showsVerticalScrollIndicator={false}
              ListEmptyComponent={
                <View style={styles.emptyContainer}>
                  <Text style={styles.emptyIcon}>🔍</Text>
                  <Text style={styles.emptyText}>
                    {searchQuery ? '未找到匹配的充电站' : '暂无充电站数据'}
                  </Text>
                  {!searchQuery && (
                    <TouchableOpacity
                      style={styles.emptyButton}
                      onPress={handleRefresh}
                    >
                      <Text style={styles.emptyButtonText}>刷新</Text>
                    </TouchableOpacity>
                  )}
                </View>
              }
            />
          ) : Platform.OS === 'web' || !CustomMapView ? (
            <View style={styles.mapPlaceholder}>
              <Text style={styles.placeholderIcon}>🗺️</Text>
              <Text style={styles.placeholderText}>地图视图</Text>
              <Text style={styles.placeholderSubtext}>
                地图功能在Web平台受限{'\n'}
                请在移动设备上查看完整功能
              </Text>
            </View>
          ) : (
            <CustomMapView
              style={styles.mapContainer}
              centerCoordinate={
                userLocation || [
                  MAP_CONFIG.DEFAULT_LONGITUDE,
                  MAP_CONFIG.DEFAULT_LATITUDE,
                ]
              }
              zoomLevel={MAP_CONFIG.DEFAULT_ZOOM}
              onMapReady={() => setMapReady(true)}
            >
              {mapReady && filteredChargers.length > 0 && ClusteredMarkers && (
                <ClusteredMarkers
                  chargers={filteredChargers}
                  onMarkerPress={handleMarkerPress}
                />
              )}
            </CustomMapView>
          )}
        </>
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  refreshButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  refreshIcon: {
    fontSize: 20,
  },
  filterButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  filterIcon: {
    fontSize: 20,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    marginHorizontal: 20,
    marginBottom: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  searchIcon: {
    fontSize: 20,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
    color: COLORS.TEXT_PRIMARY,
  },
  viewToggle: {
    flexDirection: 'row',
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 4,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  toggleButtonActive: {
    backgroundColor: COLORS.PRIMARY,
  },
  toggleText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.TEXT_SECONDARY,
  },
  toggleTextActive: {
    color: '#FFFFFF',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  stationCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  stationName: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  ratingIcon: {
    fontSize: 16,
    marginRight: 4,
  },
  ratingText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.TEXT_PRIMARY,
  },
  statusDot: {
    marginLeft: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  stationAddress: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: 12,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  infoIcon: {
    fontSize: 14,
    marginRight: 4,
  },
  infoText: {
    fontSize: 12,
    color: COLORS.TEXT_PRIMARY,
    fontWeight: '500',
  },
  unavailableText: {
    color: COLORS.ERROR,
  },
  loadingContainer: {
    padding: 40,
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  errorContainer: {
    padding: 20,
    alignItems: 'center',
  },
  errorText: {
    fontSize: 14,
    color: COLORS.ERROR,
    textAlign: 'center',
    marginBottom: 12,
  },
  retryButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: COLORS.PRIMARY,
    borderRadius: 8,
  },
  retryText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  emptyContainer: {
    padding: 40,
    alignItems: 'center',
  },
  emptyIcon: {
    fontSize: 60,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: 16,
  },
  emptyButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: COLORS.PRIMARY,
    borderRadius: 8,
  },
  emptyButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  mapContainer: {
    flex: 1,
  },
  mapPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#E5E7EB',
  },
  placeholderIcon: {
    fontSize: 80,
    marginBottom: 16,
  },
  placeholderText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 8,
  },
  placeholderSubtext: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    lineHeight: 20,
  },
});

export default HomeScreen;
