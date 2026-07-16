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
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchChargingRecords } from '../../store/slices/transactionsSlice';
import type { ChargingRecord } from '../../api/transactions';
import ScreenHeader from '../../components/ui/ScreenHeader';

type Nav = StackNavigationProp<RootStackParamList, 'ChargingHistory'>;

function fmtTime(s?: string | null) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

const ChargingHistoryScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const { items, loadingList, error } = useAppSelector((st) => st.transactions);

  const load = () => dispatch(fetchChargingRecords({ limit: 50, offset: 0 }));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const renderItem = ({ item }: { item: ChargingRecord }) => {
    const title = item.site_name || item.charge_point_id;
    const sub = `${fmtTime(item.start_time)}  ·  ${item.status}`;
    const energy = typeof item.energy_kwh === 'number' ? `${item.energy_kwh.toFixed(2)} kWh` : '—';
    return (
      <TouchableOpacity
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
    <SafeAreaView style={styles.container}>
      <ScreenHeader title={t.history.title} onBack={() => navigation.goBack()} />

      {!!error && <Text style={styles.errorText}>{error}</Text>}

      {loadingList && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.PRIMARY} />
          <Text style={styles.centerText}>{t.common.loading}</Text>
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyIcon}>🧾</Text>
          <Text style={styles.centerText}>{t.history.empty}</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(it) => String(it.id)}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 24 }}
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  errorText: { paddingHorizontal: 16, paddingTop: 10, color: COLORS.ERROR, fontWeight: '700' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerText: { marginTop: 10, color: COLORS.TEXT_SECONDARY },
  emptyIcon: { fontSize: 56, marginBottom: 10 },
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

