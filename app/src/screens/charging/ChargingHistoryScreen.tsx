/**
 * 充电记录列表（PAY-MP-002 authoritative projection）
 *
 * P001 remains available through the legacy transactions adapter. This screen
 * opts into P002 explicitly so financial labels come from the server-owned
 * projection instead of being inferred from the old session status.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import { localizeStatus } from '../../utils/localizeStatus';
import { formatDateTime, publicChargerIdentity } from '../../utils/localizedDisplay';
import { getP002Transactions, PayMp002Error } from '../../features/payMp002/adapter';
import type { P002PaymentStatus, P002TransactionProjection } from '../../features/payMp002/types';
import Button from '../../components/ui/Button';

type Nav = StackNavigationProp<RootStackParamList, 'ChargingHistory'>;

const formatDecimalAmount = (amount: string, currency: string): string => {
  const match = amount.trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return `${amount} ${currency}`;
  const [, sign, integer, fraction = ''] = match;
  const groupedInteger = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const decimal = fraction ? `,${fraction}` : '';
  const symbol = currency === 'COP' ? '$' : '';
  return `${sign}${symbol}${groupedInteger}${decimal} ${currency}`.trim();
};

const paymentStatusLabel = (status: P002PaymentStatus | undefined, t: ReturnType<typeof useI18n>['t']) => {
  switch (status) {
    case 'paid': return t.history.billingPaid;
    case 'processing': return t.history.billingProcessing;
    case 'unpaid': return t.history.billingUnpaid;
    case 'refunded': return t.history.billingRefunded;
    case 'partially_refunded': return t.history.billingPartiallyRefunded;
    case 'disputed': return t.history.billingDisputed;
    default: return t.history.pendingSettlement;
  }
};

const dataQualityLabel = (
  quality: P002TransactionProjection['data_quality'],
  t: ReturnType<typeof useI18n>['t'],
) => {
  switch (quality) {
    case 'current': return t.history.dataQualityCurrent;
    case 'legacy': return t.history.dataQualityLegacy;
    default: return t.history.dataQualityUnknown;
  }
};

const ChargingHistoryScreen = () => {
  const { t, locale } = useI18n();
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<P002TransactionProjection[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<PayMp002Error | null>(null);

  const load = useCallback(async (cursor?: string, replace = false) => {
    if (cursor) setLoadingMore(true);
    else if (replace) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const page = await getP002Transactions({ limit: 50, ...(cursor ? { cursor } : {}) });
      setItems((current) => replace || !cursor ? page.items : [...current, ...page.items]);
      setNextCursor(page.page.next_cursor);
      setHasMore(page.page.has_more);
    } catch (cause) {
      setError(cause instanceof PayMp002Error ? cause : null);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const renderItem = ({ item }: { item: P002TransactionProjection }) => {
    const title = item.site_name || publicChargerIdentity(item, t.common.unknown);
    const sub = `${formatDateTime(item.start_time, locale)}  ·  ${localizeStatus(item.status, t)}`;
    const energy = item.energy_kwh ? `${item.energy_kwh} kWh` : '—';
    const amount = item.invoice?.amount && item.invoice.currency
      ? formatDecimalAmount(item.invoice.amount, item.invoice.currency)
      : t.history.pendingSettlement;
    const paymentLabel = paymentStatusLabel(item.payment_status, t);
    return (
      <TouchableOpacity
        testID="app-history-row"
        accessibilityLabel={`${title}, ${sub}, ${energy}, ${paymentLabel}`}
        accessibilityRole="button"
        style={styles.card}
        onPress={() => navigation.navigate('ChargingHistoryDetail', { id: item.id })}
      >
        <View style={styles.row}>
          <View style={styles.left}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subTitle}>{sub}</Text>
            <Text testID="app-history-payment-status" style={styles.paymentStatus}>{paymentLabel}</Text>
            <Text style={styles.quality}>{t.history.dataQuality}: {dataQualityLabel(item.data_quality, t)}</Text>
          </View>
          <View style={styles.right}>
            <Text style={styles.energy}>{energy}</Text>
            <Text style={styles.amount}>{amount}</Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Screen testID="app-history-screen" accessibilityLabel={t.history.title}>
      <ScreenHeader title={t.history.title} onBack={() => navigation.goBack()} />
      {!!error && <Text style={styles.errorText}>{t.history.loadFailed}</Text>}
      {loading && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.centerText}>{t.common.loading}</Text>
        </View>
      ) : error && items.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{t.history.loadFailed}</Text>
          <Button title={t.common.retry} onPress={() => void load()} variant="outline" size="small" style={styles.retry} />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.centerText}>{t.history.empty}</Text>
        </View>
      ) : (
        <FlatList
          testID="app-history-list"
          data={items}
          keyExtractor={(it) => String(it.id)}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 24 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(undefined, true)} />}
          onEndReached={() => {
            if (hasMore && nextCursor && !loadingMore) void load(nextCursor);
          }}
          onEndReachedThreshold={0.5}
          ListFooterComponent={loadingMore ? <ActivityIndicator color={COLORS.PRIMARY} /> : null}
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  errorText: { paddingHorizontal: 16, paddingTop: 10, color: COLORS.ERROR, fontWeight: '700' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerText: { marginTop: 10, color: COLORS.TEXT_SECONDARY },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    marginBottom: 10,
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  left: { flex: 1, paddingRight: 10 },
  right: { alignItems: 'flex-end', paddingLeft: 8 },
  title: { fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  paymentStatus: { marginTop: 8, color: COLORS.TEXT_PRIMARY, fontWeight: '800' },
  quality: { marginTop: 4, color: COLORS.TEXT_SECONDARY, fontSize: 11 },
  energy: { fontWeight: '900', color: COLORS.PRIMARY },
  amount: { marginTop: 6, color: COLORS.TEXT_PRIMARY, fontWeight: '800', fontSize: 12 },
  retry: { marginTop: 12 },
});

export default ChargingHistoryScreen;
