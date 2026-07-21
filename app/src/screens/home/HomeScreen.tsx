/**
 * 主页 - 充电站列表和地图视图
 */

import React, { useMemo, useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { COLORS, MAP_CONFIG, IOS_STYLES } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchSites } from '../../store/slices/siteSlice';
import type { SiteSummary } from '../../api/sites';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { Platform } from 'react-native';
import GoogleMapView, { type MapMarker } from '../../components/GoogleMapView';
import Icon from '../../components/ui/Icon';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge, { BadgeVariant } from '../../components/ui/Badge';
import TextField from '../../components/ui/TextField';
import { useI18n } from '../../i18n';
import { SkeletonCard } from '../../components/ui/Skeleton';
import { formatDistance } from '../../utils/formatDistance';
import BrandLogo from '../../components/brand/BrandLogo';
import { connectorStandardLabel } from '../../utils/connectorDisplay';
import {
  getSiteStatusBreakdown,
  getSiteStatusColor,
  getSiteAvailability,
} from '../../utils/siteStatus';

const HomeScreen = () => {
  const { t } = useI18n();

  const dispatch = useAppDispatch();
  const { sites, loading, error } = useAppSelector((state) => state.site);
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
        
        dispatch(fetchSites({
          latitude: location.coords.latitude,
          longitude: location.coords.longitude,
          radius: MAP_CONFIG.SEARCH_RADIUS,
        }));
      } else {
        dispatch(fetchSites(undefined));
      }
    } catch (err) {
      console.error('Failed to load sites:', err);
      // 出错时也获取所有充电站
      dispatch(fetchSites(undefined));
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadChargers();
    setRefreshing(false);
  };

  const handleMarkerPress = (site: SiteSummary) => {
    navigation.navigate('StationDetail', { siteId: site.id });
  };

  const renderStationCard = ({ item, index }: { item: SiteSummary; index: number }) => {
    const available = item.available_connectors || 0;
    const total = item.total_connectors || 0;
    const isAvailable = available > 0;
    const siteAvailability = getSiteAvailability(available, item.status_counts, item.status);
    const statusVariant: BadgeVariant = siteAvailability === 'availableToCharge'
      ? 'success'
      : siteAvailability === 'siteNoConnectorsFree'
      ? 'warning'
      : 'error';
    const statusLabel = t.station[siteAvailability];
    const statusBreakdown = getSiteStatusBreakdown(item.status_counts);
    const visibleOptions = item.charging_options.slice(0, 3);

    return (
      <Card
        key={item.id}
        onPress={() => handleMarkerPress(item)}
        interactive={true}
        style={[styles.stationCard, { marginBottom: index < filteredSites.length - 1 ? IOS_STYLES.SPACING.MD : 0 }]}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.stationName} numberOfLines={1}>
            {item.name}
          </Text>
          <Badge label={statusLabel} variant={statusVariant} dot />
        </View>

        <View style={styles.addressRow}>
          <Text style={styles.stationAddress} numberOfLines={1}>
            {item.address || t.home.addressUnknown}
          </Text>
          {item.distance_km !== undefined && (
            <Text style={styles.distanceText}>{formatDistance(item.distance_km)}</Text>
          )}
        </View>

        {statusBreakdown.length > 0 && (
          <Text style={styles.statusBreakdown}>
            {statusBreakdown.map(({ status, count }, statusIndex) => (
              <React.Fragment key={status}>
                {statusIndex > 0 && <Text style={styles.statusSeparator}> · </Text>}
                <Text style={{ color: getSiteStatusColor(status) }}>
                  {count} {t.status[status].toLocaleLowerCase()}
                </Text>
              </React.Fragment>
            ))}
          </Text>
        )}

        {visibleOptions.length > 0 ? (
          <View style={styles.chargingOptions}>
            {visibleOptions.map((option) => {
              const standardLabel = connectorStandardLabel(option.standard) || t.station.connectorTypeUnknown;
              const capability = [
                option.current_type,
                typeof option.max_power_kw === 'number' ? `${option.max_power_kw} kW` : null,
              ].filter(Boolean).join(' · ');
              const optionBreakdown = getSiteStatusBreakdown(option.status_counts);
              return (
                <View
                  key={`${option.standard}-${option.current_type || 'unknown'}-${option.max_power_kw ?? 'unknown'}`}
                  style={styles.chargingOptionRow}
                >
                  <View style={styles.chargingOptionIdentity}>
                    <Text style={styles.chargingOptionStandard}>{standardLabel}</Text>
                    {!!capability && <Text style={styles.chargingOptionCapability}>{capability}</Text>}
                  </View>
                  <View style={styles.chargingOptionStatus}>
                    <Text style={[
                      styles.chargingOptionAvailability,
                      option.available === 0 && styles.unavailableText,
                    ]}>
                      {option.available}/{option.total} {t.home.available}
                    </Text>
                    {optionBreakdown.length > 0 && (
                      <Text style={styles.optionStatusBreakdown}>
                        {optionBreakdown.map(({ status, count }, statusIndex) => (
                          <React.Fragment key={status}>
                            {statusIndex > 0 && <Text style={styles.statusSeparator}> · </Text>}
                            <Text style={{ color: getSiteStatusColor(status) }}>
                              {count} {t.status[status].toLocaleLowerCase()}
                            </Text>
                          </React.Fragment>
                        ))}
                      </Text>
                    )}
                  </View>
                </View>
              );
            })}
            {item.charging_options.length > visibleOptions.length && (
              <Text style={styles.moreOptionsText}>
                {t.home.moreChargingOptions.replace(
                  '{count}',
                  String(item.charging_options.length - visibleOptions.length),
                )}
              </Text>
            )}
          </View>
        ) : null}

        <View style={styles.cardFooter}>
          {visibleOptions.length === 0 ? (
            <Text style={[styles.availabilityText, !isAvailable && styles.unavailableText]}>
              {available}/{total} {t.home.available}
            </Text>
          ) : <View />}

          {!!item.price_per_kwh && (
            <Text style={styles.priceText}>${item.price_per_kwh.toFixed(2)}/kWh</Text>
          )}
        </View>
      </Card>
    );
  };

  // 筛选充电站（根据搜索词）
  const filteredSites = sites.filter((site) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      site.name.toLowerCase().includes(query) ||
      site.address.toLowerCase().includes(query) ||
      site.connector_types.some((type) => type.toLowerCase().includes(query))
    );
  });

  const mapMarkers: MapMarker[] = useMemo(() => {
    return filteredSites
      .map((site) => ({
        id: site.id,
        latitude: site.latitude,
        longitude: site.longitude,
        title: site.name,
        description: site.address,
        status: site.status,
        available: site.available_connectors,
      }));
  }, [filteredSites]);

  const mapCenter = useMemo(() => {
    if (userLocation) return { latitude: userLocation[1], longitude: userLocation[0] };
    return { latitude: MAP_CONFIG.DEFAULT_LATITUDE, longitude: MAP_CONFIG.DEFAULT_LONGITUDE };
  }, [userLocation]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      {/* Header */}
      <View style={styles.header}>
        <BrandLogo compact style={styles.headerLogo} accessibilityLabel="EsLatin" />
        <TouchableOpacity
          style={styles.refreshButton}
          onPress={handleRefresh}
          accessibilityRole="button"
          accessibilityLabel={t.common.refresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <Text style={styles.refreshPending}>···</Text>
          ) : (
            <Icon name="refresh" library="Ionicons" size={20} color={COLORS.TEXT_PRIMARY} />
          )}
        </TouchableOpacity>
      </View>

      <View style={styles.hero}>
        <Text style={styles.headerTitle}>{t.home.title}</Text>
        <Text style={styles.headerSubtitle}>{t.home.subtitle}</Text>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <TextField
          containerStyle={styles.searchField}
          inputStyle={styles.searchInput}
          placeholder={t.home.search}
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
          <Text style={styles.stateTitle}>{t.common.retry}</Text>
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
              {t.home.list} ({filteredSites.length})
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
              data={filteredSites}
              renderItem={({ item, index }) => renderStationCard({ item, index })}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              showsVerticalScrollIndicator={false}
              ListEmptyComponent={
                <View style={styles.emptyContainer}>
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
                const site = filteredSites.find((item) => item.id === m.id);
                if (site) handleMarkerPress(site);
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
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 4,
  },
  headerLogo: {
    width: 112,
    height: 108,
  },
  hero: {
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    paddingHorizontal: 20,
    marginTop: -4,
    marginBottom: 18,
  },
  headerTitle: {
    fontSize: 30,
    lineHeight: 36,
    fontWeight: '800',
    color: COLORS.TEXT_PRIMARY,
    letterSpacing: -0.6,
  },
  headerSubtitle: {
    marginTop: 6,
    maxWidth: 420,
    fontSize: 15,
    lineHeight: 22,
    color: COLORS.TEXT_SECONDARY,
  },
  refreshButton: {
    width: 42,
    height: 42,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 21,
    backgroundColor: COLORS.IOS_WHITE,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  refreshPending: {
    color: COLORS.TEXT_SECONDARY,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1,
  },
  searchContainer: {
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    paddingHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.MD,
  },
  searchField: { flex: 1 },
  searchInput: {
    flex: 1,
    fontSize: 16,
    color: COLORS.TEXT_PRIMARY,
  },
  viewToggle: {
    width: '94%',
    maxWidth: 920,
    alignSelf: 'center',
    flexDirection: 'row',
    marginBottom: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: IOS_STYLES.RADIUS.ROUND,
    padding: 3,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: IOS_STYLES.RADIUS.ROUND,
  },
  toggleButtonActive: {
    backgroundColor: COLORS.TEXT_PRIMARY,
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
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  stationCard: {
    padding: 18,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
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
    marginBottom: 10,
  },
  stationAddress: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
    flex: 1,
    marginRight: IOS_STYLES.SPACING.SM,
  },
  distanceText: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
    fontWeight: IOS_STYLES.FONT_WEIGHT.MEDIUM,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  chargingOptions: {
    marginTop: 8,
    marginBottom: 14,
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  chargingOptionRow: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 9,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.BORDER,
  },
  chargingOptionIdentity: { flex: 1, flexDirection: 'row', alignItems: 'baseline' },
  chargingOptionStandard: {
    minWidth: 70,
    marginRight: 10,
    color: COLORS.TEXT_PRIMARY,
    fontSize: 14,
    fontWeight: '700',
  },
  chargingOptionCapability: { color: COLORS.TEXT_SECONDARY, fontSize: 13 },
  chargingOptionAvailability: {
    color: COLORS.PRIMARY_DARK,
    fontSize: 13,
    fontWeight: '700',
  },
  chargingOptionStatus: { flexShrink: 1, alignItems: 'flex-end', marginLeft: 12 },
  statusBreakdown: { fontSize: 12, fontWeight: '600', lineHeight: 18 },
  optionStatusBreakdown: { marginTop: 3, fontSize: 11, fontWeight: '600', lineHeight: 16 },
  statusSeparator: { color: COLORS.TEXT_TERTIARY },
  moreOptionsText: {
    marginTop: 8,
    color: COLORS.TEXT_SECONDARY,
    fontSize: 12,
    fontWeight: '600',
  },
  availabilityText: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.PRIMARY_DARK,
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
  },
  priceText: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
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
  stateTitle: {
    fontSize: IOS_STYLES.FONT_SIZE.LARGE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    color: COLORS.TEXT_PRIMARY,
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
