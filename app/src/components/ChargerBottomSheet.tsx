/**
 * 充电站详情底部抽屉组件
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  ScrollView,
  Dimensions,
} from 'react-native';
import { COLORS } from '../constants/config';
import { ChargerDetail } from '../api/chargers';
import { useI18n } from '../i18n';
import { localizeStatus } from '../utils/localizeStatus';
import { formatDateTime, publicChargerIdentity } from '../utils/localizedDisplay';
import { formatPricing } from '../utils/pricing';
import Icon from './ui/Icon';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

interface ChargerBottomSheetProps {
  visible: boolean;
  charger: ChargerDetail | null;
  onClose: () => void;
  onNavigate?: (charger: ChargerDetail) => void;
  onStartCharging?: (charger: ChargerDetail) => void;
}

const ChargerBottomSheet: React.FC<ChargerBottomSheetProps> = ({
  visible,
  charger,
  onClose,
  onNavigate,
  onStartCharging,
}) => {
  const { t, locale } = useI18n();
  if (!charger) return null;
  const priceLabel = formatPricing(charger.pricing, t, locale);

  const isAvailable = (charger.available_connectors || 0) > 0;
  const statusColor =
    charger.status === 'Offline'
      ? COLORS.ERROR
      : isAvailable
      ? COLORS.SUCCESS
      : COLORS.WARNING;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <TouchableOpacity
        style={styles.overlay}
        activeOpacity={1}
        onPress={onClose}
      >
        <View style={styles.container}>
          <TouchableOpacity activeOpacity={1} onPress={(e) => e.stopPropagation()}>
            {/* Handle Bar */}
            <View style={styles.handleBar} />

            <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
              {/* Header */}
              <View style={styles.header}>
                <View style={styles.headerTop}>
                  <Text style={styles.title}>
                    {charger.site_name || t.home.stationFallback.replace('{id}', publicChargerIdentity(charger, t.common.unknown))}
                  </Text>
                  <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
                    <Text style={styles.statusText}>{localizeStatus(charger.status, t)}</Text>
                  </View>
                </View>
                
                {charger.site_address && (
                  <Text style={styles.address}>{charger.site_address}</Text>
                )}
              </View>

              {/* Stats Grid */}
              <View style={styles.statsGrid}>
                <View style={styles.statItem}>
                  <Icon name="flash-outline" size={24} color={COLORS.PRIMARY} style={styles.statIcon} />
                  <Text style={styles.statValue}>
                    {charger.available_connectors || 0}/{charger.total_connectors || 0}
                  </Text>
                  <Text style={styles.statLabel}>{t.station.connectors}</Text>
                </View>

                {priceLabel && (
                  <View style={styles.statItem}>
                    <Icon name="cash-outline" size={24} color={COLORS.PRIMARY} style={styles.statIcon} />
                    <Text style={styles.statValue}>{priceLabel}</Text>
                    <Text style={styles.statLabel}>{t.station.price}</Text>
                  </View>
                )}

                {charger.charging_rate && (
                  <View style={styles.statItem}>
                    <Icon name="speedometer-outline" size={24} color={COLORS.PRIMARY} style={styles.statIcon} />
                    <Text style={styles.statValue}>{charger.charging_rate}kW</Text>
                    <Text style={styles.statLabel}>{t.station.power}</Text>
                  </View>
                )}

                {charger.rating && (
                  <View style={styles.statItem}>
                    <Icon name="star-outline" size={24} color={COLORS.PRIMARY} style={styles.statIcon} />
                    <Text style={styles.statValue}>{charger.rating.toFixed(1)}</Text>
                    <Text style={styles.statLabel}>{t.station.rating}</Text>
                  </View>
                )}
              </View>

              {/* Details */}
              <View style={styles.detailsSection}>
                <Text style={styles.sectionTitle}>{t.station.details}</Text>
                
                {charger.vendor && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>{t.station.vendor}</Text>
                    <Text style={styles.detailValue}>{charger.vendor}</Text>
                  </View>
                )}

                {charger.model && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>{t.station.model}</Text>
                    <Text style={styles.detailValue}>{charger.model}</Text>
                  </View>
                )}

                {charger.connector_type && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>{t.station.connectorType}</Text>
                    <Text style={styles.detailValue}>{charger.connector_type}</Text>
                  </View>
                )}

                {charger.last_seen && (
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>{t.station.lastOnline}</Text>
                    <Text style={styles.detailValue}>
                      {formatDateTime(charger.last_seen, locale)}
                    </Text>
                  </View>
                )}
              </View>

              {/* Description */}
              {charger.description && (
                <View style={styles.descriptionSection}>
                  <Text style={styles.sectionTitle}>{t.station.description}</Text>
                  <Text style={styles.description}>{charger.description}</Text>
                </View>
              )}
            </ScrollView>

            {/* Action Buttons */}
            <View style={styles.actions}>
              {onNavigate && charger.latitude && charger.longitude && (
                <TouchableOpacity
                  style={[styles.actionButton, styles.navigationButton]}
                  onPress={() => onNavigate(charger)}
                >
                  <Icon name="navigate-outline" size={18} color="#FFFFFF" style={styles.actionIcon} />
                  <Text style={styles.navigationButtonText}>{t.station.navigate}</Text>
                </TouchableOpacity>
              )}

              {onStartCharging && isAvailable && (
                <TouchableOpacity
                  style={[styles.actionButton, styles.chargeButton]}
                  onPress={() => onStartCharging(charger)}
                >
                  <Icon name="flash-outline" size={18} color="#FFFFFF" style={styles.actionIcon} />
                  <Text style={styles.chargeButtonText}>{t.station.startCharge}</Text>
                </TouchableOpacity>
              )}

              {!isAvailable && (
                <View style={[styles.actionButton, styles.disabledButton]}>
                  <Text style={styles.disabledButtonText}>{t.station.noAvailable}</Text>
                </View>
              )}
            </View>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  container: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: SCREEN_HEIGHT * 0.75,
    paddingBottom: 20,
  },
  handleBar: {
    width: 40,
    height: 4,
    backgroundColor: COLORS.BORDER,
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: 12,
    marginBottom: 8,
  },
  content: {
    maxHeight: SCREEN_HEIGHT * 0.55,
  },
  header: {
    padding: 20,
    paddingBottom: 16,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    flex: 1,
    marginRight: 12,
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  address: {
    fontSize: 15,
    color: COLORS.TEXT_SECONDARY,
    lineHeight: 20,
  },
  statsGrid: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: COLORS.BORDER,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statIcon: {
    marginBottom: 6,
  },
  statValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 4,
  },
  statLabel: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
  },
  detailsSection: {
    padding: 20,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: 12,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.BORDER,
  },
  detailLabel: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.TEXT_PRIMARY,
  },
  descriptionSection: {
    padding: 20,
    paddingTop: 0,
  },
  description: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
    lineHeight: 20,
  },
  actions: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    paddingTop: 16,
  },
  actionButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
  },
  actionIcon: {
    marginRight: 8,
  },
  // 兼容 RN Web / 旧 RN：不用 gap，改用按钮自身 margin
  navigationButton: {
    backgroundColor: COLORS.SECONDARY,
    marginRight: 12,
  },
  navigationButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  chargeButton: {
    backgroundColor: COLORS.PRIMARY,
  },
  chargeButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  disabledButton: {
    backgroundColor: COLORS.DISABLED,
  },
  disabledButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.TEXT_SECONDARY,
  },
});

export default ChargerBottomSheet;
