/**
 * 充电站详情页（Phase 2.4）
 * 展示站点信息、状态、价格、连接器列表等
 */
 
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StatusBar,
  RefreshControl,
  Platform,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS, IOS_STYLES } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchSiteById } from '../../store/slices/siteSlice';
import GoogleMapView from '../../components/GoogleMapView';
import Button from '../../components/ui/Button';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Badge, { BadgeVariant } from '../../components/ui/Badge';
import { radius, spacing, typography } from '../../theme';
import Icon from '../../components/ui/Icon';
import { removeFavoriteSite, saveFavoriteSite } from '../../api/favorites';
import { connectorStandardLabel } from '../../utils/connectorDisplay';
import { localizeStatus } from '../../utils/localizeStatus';
import {
  getSiteStatusBreakdown,
  getSiteStatusColor,
  getSiteAvailability,
  hasChargingWithoutAvailability,
} from '../../utils/siteStatus';
import {
  hasValidNavigationCoordinates,
  showExternalNavigationOptions,
} from '../../utils/externalNavigation';

type StationDetailRouteProp = RouteProp<RootStackParamList, 'StationDetail'>;
type StationDetailNavProp = StackNavigationProp<RootStackParamList, 'StationDetail'>;

const StationDetailScreen = () => {
  const { t } = useI18n();

  const dispatch = useAppDispatch();
  const navigation = useNavigation<StationDetailNavProp>();
  const route = useRoute<StationDetailRouteProp>();

  const { siteId } = route.params;
  const { selectedSite, loading, error } = useAppSelector((state) => state.site);
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState(false);

  const loadDetail = async () => {
    try {
      await dispatch(fetchSiteById(siteId)).unwrap();
    } catch {
      // 错误由 slice 写入 error，这里不额外弹窗，避免干扰
    }
  };

  useEffect(() => {
    loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  const site = selectedSite && selectedSite.id === siteId ? selectedSite : null;

  useEffect(() => {
    if (site) setIsFavorite(site.is_favorite);
  }, [site]);

  const isAvailable = (site?.available_connectors || 0) > 0;
  const noConnectorsFree = hasChargingWithoutAvailability(
    site?.available_connectors || 0,
    site?.status_counts,
  );
  const siteAvailability = site
    ? getSiteAvailability(site.available_connectors, site.status_counts, site.status)
    : null;
  const statusVariant: BadgeVariant = !site
    ? 'neutral'
    : siteAvailability === 'availableToCharge'
    ? 'success'
    : siteAvailability === 'siteNoConnectorsFree'
    ? 'warning'
    : 'error';
  const statusLabel = siteAvailability ? t.station[siteAvailability] : '';
  const statusBreakdown = getSiteStatusBreakdown(site?.status_counts);

  const handleNavigate = () => {
    if (!site || !hasValidNavigationCoordinates(site.latitude, site.longitude)) {
      Alert.alert(t.station.navUnavailable, t.station.navNoCoords);
      return;
    }

    showExternalNavigationOptions({
      latitude: Number(site.latitude),
      longitude: Number(site.longitude),
      label: site.name,
      copy: {
        title: t.station.chooseNavigationApp,
        message: t.station.chooseNavigationAppHint,
        googleMaps: t.station.googleMaps,
        waze: t.station.waze,
        appleMaps: t.station.appleMaps,
        cancel: t.common.cancel,
        openFailedTitle: t.station.navUnavailable,
        openFailedMessage: t.station.navOpenFailed,
      },
    });
  };

  const handleStartCharging = () => {
    // 爆改测试版：启动充电必须扫码获取 qr_token
    // Scan 在 Tab 导航器中，需要通过 MainTabs 导航
    navigation.navigate('MainTabs', { screen: 'Scan' });
  };

  const handleToggleFavorite = async () => {
    if (!site || favoriteBusy) return;
    const next = !isFavorite;
    setFavoriteBusy(true);
    try {
      if (next) await saveFavoriteSite(site.id);
      else await removeFavoriteSite(site.id);
      setIsFavorite(next);
    } catch {
      Alert.alert(t.common.error, t.saved.loadFailed);
    } finally {
      setFavoriteBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" />

      <ScreenHeader
        title={t.station.title}
        onBack={() => navigation.goBack()}
        right={
          <TouchableOpacity
            testID="app-station-favorite-toggle"
            accessibilityRole="button"
            accessibilityLabel={isFavorite ? t.saved.remove : t.saved.save}
            disabled={!site || favoriteBusy}
            style={styles.favoriteButton}
            onPress={handleToggleFavorite}
          >
            <Icon
              name={isFavorite ? 'bookmark' : 'bookmark-outline'}
              library="Ionicons"
              size={22}
              color={isFavorite ? COLORS.PRIMARY : COLORS.TEXT_SECONDARY}
            />
          </TouchableOpacity>
        }
      />

      <ScrollView
        style={styles.content}
        refreshControl={<RefreshControl refreshing={false} onRefresh={loadDetail} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Loading */}
        {loading && !site && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={COLORS.PRIMARY} />
            <Text style={styles.loadingText}>{t.station.loading}</Text>
          </View>
        )}

        {/* Error */}
        {!!error && !site && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorTitle}>{t.station.loadFailed}</Text>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={loadDetail}>
              <Text style={styles.retryText}>{t.common.retry}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Empty */}
        {!loading && !error && !site && (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>{t.station.notFound}</Text>
            <Text style={styles.emptyText}>{t.station.notFoundHint}</Text>
            <Button title={t.station.reload} onPress={loadDetail} variant="primary" size="medium" />
          </View>
        )}

        {/* Detail */}
        {!!site && (
          <>
            {/* 基本信息 */}
            <View style={styles.card}>
              <View style={styles.titleRow}>
                <View style={styles.titleLeft}>
                  <Text style={styles.title}>
                    {site.name}
                  </Text>
                  <Text style={styles.subTitle}>{site.address || t.home.addressUnknown}</Text>
                </View>
                <Badge label={statusLabel} variant={statusVariant} />
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

              <View style={styles.metricsRow}>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>{t.station.connectors}</Text>
                  <Text style={styles.metricValue}>
                    {site.available_connectors || 0}/{site.total_connectors || 0}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>{t.station.price}</Text>
                  <Text style={styles.metricValue}>
                    {typeof site.price_per_kwh === 'number'
                      ? `$${site.price_per_kwh.toFixed(2)}/kWh`
                      : t.common.na}
                  </Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricLabel}>{t.station.power}</Text>
                  <Text style={styles.metricValue}>
                    {typeof site.max_power_kw === 'number' ? `${site.max_power_kw} kW` : t.common.na}
                  </Text>
                </View>
              </View>
            </View>

            {/* 地图（仅 iOS/Android，展示站点位置） */}
            {Platform.OS !== 'web' && typeof site.latitude === 'number' && typeof site.longitude === 'number' && (
              <View style={styles.card}>
                <Text style={styles.sectionTitle}>{t.station.location}</Text>
                <View style={styles.mapWrap}>
                  <GoogleMapView
                    style={styles.map}
                    center={{ latitude: site.latitude, longitude: site.longitude }}
                    zoomDelta={0.02}
                    markers={[
                      {
                        id: site.id,
                        latitude: site.latitude,
                        longitude: site.longitude,
                        title: site.name,
                        description: site.address,
                        status: site.status,
                        available: site.available_connectors,
                      },
                    ]}
                    showsUserLocation={true}
                  />
                </View>
              </View>
            )}

            {/* 面向司机的充电桩与连接器标签；不得回退显示内部 UUID 或 OCPP 身份。 */}
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>{t.station.chargersTitle}</Text>
              {site.charge_points.length > 0 ? (
                site.charge_points.map((chargePoint) => {
                  const chargerTitle = chargePoint.display_name?.trim() || chargePoint.display_code;
                  return (
                    <View
                      key={chargePoint.id}
                      testID={`app-public-charger-${chargePoint.display_code}`}
                      style={styles.chargerCard}
                    >
                      <View style={styles.chargerHeader}>
                        <View style={styles.chargerTitleBlock}>
                          <Text style={styles.chargerName}>{chargerTitle}</Text>
                          {!!chargePoint.display_name && (
                            <Text style={styles.chargerCode}>{chargePoint.display_code}</Text>
                          )}
                          {!!chargePoint.location_hint && (
                            <Text style={styles.locationHint}>{chargePoint.location_hint}</Text>
                          )}
                        </View>
                        <Badge
                          label={localizeStatus(chargePoint.status, t)}
                          variant={chargePoint.status.toLowerCase() === 'available' ? 'success' : 'neutral'}
                        />
                      </View>
                      {chargePoint.connectors.map((connector) => {
                        const connectorLabel = connector.physical_reference?.trim()
                          || t.station.connector.replace('{number}', String(connector.connector_number));
                        const standardLabel = connectorStandardLabel(connector.connector_type || '')
                          || t.station.connectorTypeUnknown;
                        const capability = [
                          standardLabel,
                          typeof connector.power_kw === 'number'
                            ? `${connector.power_kw} kW`
                            : t.station.powerUnknown,
                        ].join(' · ');
                        return (
                          <View
                            key={connector.id}
                            testID={`app-public-connector-${connector.id}`}
                            style={styles.connectorRow}
                          >
                            <View style={styles.connectorIdentity}>
                              <View style={styles.connectorIcon}>
                                <Icon name="flash-outline" library="Ionicons" size={18} color={COLORS.PRIMARY_DARK} />
                              </View>
                              <View style={styles.connectorLeft}>
                                <Text style={styles.connectorName}>{connectorLabel}</Text>
                                <Text style={styles.connectorMeta}>{capability}</Text>
                              </View>
                            </View>
                            <Text style={styles.connectorStatus}>{localizeStatus(connector.status, t)}</Text>
                          </View>
                        );
                      })}
                    </View>
                  );
                })
              ) : (
                <View style={styles.emptyBlock}>
                  <Text style={styles.emptyBlockText}>{t.station.noConnectors}</Text>
                </View>
              )}
            </View>
          </>
        )}
      </ScrollView>

      {/* Bottom actions */}
      <View style={styles.bottomBar}>
        <Button
          title={t.station.navigate}
          onPress={handleNavigate}
          variant="secondary"
          size="large"
          style={{ flex: 1, marginRight: 10 }}
        />
        <Button
          title={isAvailable
            ? t.station.startCharge
            : noConnectorsFree
            ? t.station.noConnectorsFree
            : t.station.noAvailable}
          onPress={handleStartCharging}
          variant="primary"
          size="large"
          disabled={!isAvailable}
          style={{ flex: 1 }}
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  content: { flex: 1, width: '100%', maxWidth: 960, alignSelf: 'center', padding: 16 },
  favoriteButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },

  loadingContainer: { paddingVertical: 40, alignItems: 'center' },
  loadingText: { marginTop: 10, color: COLORS.TEXT_SECONDARY },

  errorContainer: { paddingVertical: 24, alignItems: 'center' },
  errorTitle: { fontSize: 16, fontWeight: '700', color: COLORS.ERROR, marginBottom: 8 },
  errorText: { color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },
  retryButton: {
    backgroundColor: COLORS.PRIMARY,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
  },
  retryText: { color: COLORS.IOS_WHITE, fontWeight: '700' },

  emptyContainer: { paddingVertical: 32, alignItems: 'center', gap: IOS_STYLES.SPACING.MD },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: COLORS.TEXT_PRIMARY, marginBottom: 6 },
  emptyText: { color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: 16 },


  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: radius.lg,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  titleLeft: { flex: 1, paddingRight: 12 },
  title: { fontSize: 18, fontWeight: typography.bold, color: COLORS.TEXT_PRIMARY, marginBottom: 6 },
  subTitle: { color: COLORS.TEXT_SECONDARY, lineHeight: 20 },
  statusBreakdown: { marginTop: 10, fontSize: 12, fontWeight: typography.semibold, lineHeight: 18 },
  statusSeparator: { color: COLORS.TEXT_TERTIARY },

  metricsRow: { flexDirection: 'row', marginTop: 14 },
  metricItem: { flex: 1 },
  metricLabel: { color: COLORS.TEXT_SECONDARY, fontSize: 12, marginBottom: 4 },
  metricValue: { color: COLORS.TEXT_PRIMARY, fontWeight: typography.semibold },

  sectionTitle: { fontSize: 16, fontWeight: typography.semibold, color: COLORS.TEXT_PRIMARY, marginBottom: 10 },
  chargerCard: {
    marginTop: 10,
    padding: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  chargerHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  chargerTitleBlock: { flex: 1, paddingRight: 12 },
  chargerName: { color: COLORS.TEXT_PRIMARY, fontSize: 16, fontWeight: typography.bold },
  chargerCode: { marginTop: 2, color: COLORS.PRIMARY_DARK, fontSize: 13, fontWeight: typography.semibold },
  locationHint: { marginTop: 4, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  connectorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginTop: 8,
    borderRadius: radius.md,
    backgroundColor: COLORS.BACKGROUND,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  connectorIdentity: { flex: 1, flexDirection: 'row', alignItems: 'center' },
  connectorIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
    backgroundColor: COLORS.PRIMARY_SOFT,
  },
  connectorLeft: { flex: 1, paddingRight: 12 },
  connectorName: { fontSize: 15, fontWeight: typography.semibold, color: COLORS.TEXT_PRIMARY },
  connectorMeta: { marginTop: 4, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  connectorStatus: { marginLeft: 12, color: COLORS.TEXT_SECONDARY, fontSize: 12, fontWeight: typography.semibold },
  optionAvailability: { flexShrink: 1, alignItems: 'flex-end', marginLeft: 12 },
  optionAvailabilityValue: { color: COLORS.PRIMARY_DARK, fontSize: 16, fontWeight: typography.bold },
  optionUnavailableValue: { color: COLORS.ERROR },
  optionAvailabilityLabel: { marginTop: 2, color: COLORS.TEXT_SECONDARY, fontSize: 11 },
  optionStatusBreakdown: {
    marginTop: 4,
    maxWidth: 210,
    color: COLORS.TEXT_SECONDARY,
    fontSize: 11,
    fontWeight: typography.semibold,
    lineHeight: 16,
    textAlign: 'right',
  },
  emptyBlock: { paddingVertical: 16, alignItems: 'center' },
  emptyBlockText: { color: COLORS.TEXT_SECONDARY },

  mapWrap: {
    height: 220,
    borderRadius: radius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    marginTop: 10,
  },
  map: { flex: 1 },

  bottomBar: {
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    flexDirection: 'row',
    padding: spacing.md,
    backgroundColor: COLORS.IOS_WHITE,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.IOS_SEPARATOR,
  },
});

export default StationDetailScreen;
