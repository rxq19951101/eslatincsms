/**
 * 主页 - 充电站列表和地图视图
 */

import React, { useMemo, useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  FlatList,
  StatusBar,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { COLORS, MAP_CONFIG, IOS_STYLES } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargers, fetchNearbyChargers } from '../../store/slices/chargerSlice';
import { Charger } from '../../api/chargers';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { Platform } from 'react-native';
import GoogleMapView, { type MapMarker } from '../../components/GoogleMapView';
import Icon from '../../components/ui/Icon';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge, { BadgeVariant } from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { useI18n } from '../../i18n';
import { SkeletonCard } from '../../components/ui/Skeleton';
import { formatDistance } from '../../utils/formatDistance';

const HomeScreen = () => {
  const { t } = useI18n();

  const dispatch = useAppDispatch();
  const { chargers, loading, error } = useAppSelector((state) => state.charger);
  const navigation = useNavigation<StackNavigationProp<RootStackParamList>>();
  
  const [viewMode, setViewMode] = useState<'list' | 'map'>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [userLocation, setUserLocation] = useState<[number, number] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

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

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadChargers();
    setRefreshing(false);
  };

  const handleMarkerPress = (charger: Charger) => {
    // 进入详情页（Phase 2.4）
    navigation.navigate('StationDetail', { chargePointId: charger.id });
  };

  const renderStationCard = ({ item, index }: { item: Charger; index: number }) => {
    const available = item.available_connectors || 0;
    const total = item.total_connectors || 0;
    const isAvailable = available > 0;
    const statusVariant: BadgeVariant = isAvailable ? 'success' : item.status === 'Offline' ? 'error' : 'warning';

    return (
      <Card
        key={item.id}
        onPress={() => handleMarkerPress(item)}
        interactive={true}
        style={[styles.stationCard, { marginBottom: index < filteredChargers.length - 1 ? IOS_STYLES.SPACING.MD : 0 }]}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.stationName} numberOfLines={1}>
            {item.site_name || t.home.stationFallback.replace('{id}', String(item.id))}
          </Text>
          <Badge label={item.status} variant={statusVariant} dot />
        </View>

        <View style={styles.addressRow}>
          <Text style={styles.stationAddress} numberOfLines={1}>
            {item.site_address || t.home.addressUnknown}
          </Text>
          {item.distance_km !== undefined && (
            <View style={styles.distanceItem}>
              <Icon name="location" library="Ionicons" size={14} color={COLORS.TEXT_SECONDARY} />
              <Text style={styles.distanceText}>
                {formatDistance(item.distance_km)}
              </Text>
            </View>
          )}
        </View>

        <View style={styles.divider} />

        <View style={styles.cardFooter}>
          <View style={styles.infoItem}>
            <Icon name="flash" library="Ionicons" size={16} color={isAvailable ? COLORS.PRIMARY : COLORS.TEXT_SECONDARY} />
            <Text
              style={[styles.infoText, !isAvailable && styles.unavailableText]}
            >
              {available}/{total} {t.home.available}
            </Text>
          </View>

          {!!item.price_per_kwh && (
            <View style={styles.infoItem}>
              <Icon name="cash" library="Ionicons" size={16} color={COLORS.TEXT_SECONDARY} />
              <Text style={styles.infoText}>
                ${item.price_per_kwh.toFixed(2)}/kWh
              </Text>
            </View>
          )}
        </View>
      </Card>
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

  const mapMarkers: MapMarker[] = useMemo(() => {
    return filteredChargers
      .filter((c) => typeof c.latitude === 'number' && typeof c.longitude === 'number')
      .map((c) => ({
        id: c.id,
        latitude: c.latitude as number,
        longitude: c.longitude as number,
        title: c.site_name || t.home.stationFallback.replace('{id}', String(c.id)),
        description: c.site_address || '',
        status: c.status,
        available: c.available_connectors,
      }));
  }, [filteredChargers]);

  const mapCenter = useMemo(() => {
    if (userLocation) return { latitude: userLocation[1], longitude: userLocation[0] };
    return { latitude: MAP_CONFIG.DEFAULT_LATITUDE, longitude: MAP_CONFIG.DEFAULT_LONGITUDE };
  }, [userLocation]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{t.home.title}</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.refreshButton} onPress={handleRefresh}>
            <Icon
              name="refresh"
              library="Ionicons"
              size={24}
              color={COLORS.IOS_BLUE}
              animation="spin"
              animating={refreshing}
            />
          </TouchableOpacity>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <Icon name="search" library="Ionicons" size={20} color={COLORS.TEXT_SECONDARY} />
        <TextInput
          style={styles.searchInput}
          placeholder={t.home.search}
          placeholderTextColor={COLORS.TEXT_SECONDARY}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {/* 加载和错误状态 */}
      {loading && viewMode === 'list' && (
        <View style={styles.loadingContainer}>
          <SkeletonCard count={3} />
        </View>
      )}

      {error && (
        <View style={styles.errorContainer}>
          <Icon name="alert-circle" library="Ionicons" size={48} color={COLORS.ERROR} />
          <Text style={styles.errorText}>{error}</Text>
          <Button title={t.common.retry} onPress={handleRefresh} variant="primary" size="medium" />
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
              {t.home.list} ({filteredChargers.length})
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
              {t.home.map}
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
              renderItem={({ item, index }) => renderStationCard({ item, index })}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              showsVerticalScrollIndicator={false}
              ListEmptyComponent={
                <View style={styles.emptyContainer}>
                  <Icon name="search" library="Ionicons" size={60} color={COLORS.TEXT_SECONDARY} />
                  <Text style={styles.emptyText}>
                    {searchQuery ? t.home.emptySearch : t.home.empty}
                  </Text>
                  {!searchQuery && (
                    <Button title={t.common.refresh} onPress={handleRefresh} variant="primary" size="medium" />
                  )}
                </View>
              }
            />
          ) : Platform.OS === 'web' || !GoogleMapView ? (
            <View style={styles.mapPlaceholder}>
              <Icon name="map" library="Ionicons" size={80} color={COLORS.TEXT_SECONDARY} />
              <Text style={styles.placeholderText}>{t.home.mapPlaceholder}</Text>
              <Text style={styles.placeholderSubtext}>
                {t.home.mapWebLimited}
              </Text>
            </View>
          ) : (
            <GoogleMapView
              style={styles.mapContainer}
              center={mapCenter}
              zoomDelta={0.08}
              markers={mapMarkers}
              onMarkerPress={(m) => {
                const charger = filteredChargers.find((c) => c.id === m.id);
                if (charger) handleMarkerPress(charger);
              }}
              showsUserLocation={true}
            />
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
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.IOS_WHITE,
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.MD,
    paddingHorizontal: IOS_STYLES.SPACING.MD,
    paddingVertical: IOS_STYLES.SPACING.MD,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    gap: IOS_STYLES.SPACING.SM,
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
    padding: IOS_STYLES.SPACING.MD,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
    gap: IOS_STYLES.SPACING.SM,
  },
  stationName: {
    fontSize: IOS_STYLES.FONT_SIZE.LARGE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
  },
  addressRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: IOS_STYLES.SPACING.MD,
  },
  stationAddress: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
    flex: 1,
    marginRight: IOS_STYLES.SPACING.SM,
  },
  distanceItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  distanceText: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
    fontWeight: IOS_STYLES.FONT_WEIGHT.MEDIUM,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: COLORS.IOS_SEPARATOR,
    marginBottom: IOS_STYLES.SPACING.SM,
  },
  cardFooter: {
    flexDirection: 'row',
    gap: IOS_STYLES.SPACING.LG,
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  infoText: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_PRIMARY,
    fontWeight: IOS_STYLES.FONT_WEIGHT.MEDIUM,
  },
  unavailableText: {
    color: COLORS.ERROR,
  },
  loadingContainer: {
    padding: IOS_STYLES.SPACING.XL,
    paddingHorizontal: IOS_STYLES.SPACING.MD,
  },
  errorContainer: {
    padding: IOS_STYLES.SPACING.XL,
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.MD,
  },
  errorText: {
    fontSize: IOS_STYLES.FONT_SIZE.MEDIUM,
    color: COLORS.ERROR,
    textAlign: 'center',
  },
  emptyContainer: {
    padding: IOS_STYLES.SPACING.XL,
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.MD,
  },
  emptyText: {
    fontSize: IOS_STYLES.FONT_SIZE.MEDIUM,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
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
