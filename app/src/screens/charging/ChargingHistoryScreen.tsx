/**
 * 充电记录列表（订单记录）
 */

import React, { useEffect } from 'react';
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
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargingRecords } from '../../store/slices/transactionsSlice';
import type { ChargingRecord } from '../../api/transactions';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import { localizeStatus } from '../../utils/localizeStatus';
import { formatDateTime, publicChargerIdentity } from '../../utils/localizedDisplay';

type Nav = StackNavigationProp<RootStackParamList, 'ChargingHistory'>;

const ChargingHistoryScreen = () => {
  const { t, locale } = useI18n();

  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const { items, loadingList, error } = useAppSelector((st) => st.transactions);

  const load = () => dispatch(fetchChargingRecords({ limit: 50, offset: 0 }));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const renderItem = ({ item }: { item: ChargingRecord }) => {
    const title = item.site_name || publicChargerIdentity(item, t.common.unknown);
    const sub = `${formatDateTime(item.start_time, locale)}  ·  ${localizeStatus(item.status, t)}`;
    const energy = typeof item.energy_kwh === 'number' ? `${item.energy_kwh.toFixed(2)} kWh` : '—';
    return (
      <TouchableOpacity
        testID="app-history-row"
        accessibilityLabel={`${title}, ${sub}, ${energy}`}
        accessibilityRole="button"
        style={styles.card}
        onPress={() => navigation.navigate('ChargingHistoryDetail', { id: item.id })}
      >
        <View style={styles.row}>
          <View style={styles.left}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subTitle}>{sub}</Text>
          </View>
          <Text style={styles.energy}>{energy}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Screen testID="app-history-screen" accessibilityLabel={t.history.title}>
      <ScreenHeader title={t.history.title} onBack={() => navigation.goBack()} />

      {!!error && <Text style={styles.errorText}>{t.history.loadFailed}</Text>}

      {loadingList && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.centerText}>{t.common.loading}</Text>
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
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
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
  title: { fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  energy: { fontWeight: '900', color: COLORS.PRIMARY },
});

export default ChargingHistoryScreen;
