/**
 * 未付账单列表
 */
import React, { useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Alert } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList } from '../../types';
import Button from '../../components/ui/Button';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { getUnpaidCharges, payUnpaidCharge, type UnpaidCharge } from '../../api/payments';
import { formatMoneyCOP } from '../../utils/formatMoney';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import { useAppDispatch } from '../../hooks/useRedux';
import { publicChargerIdentity } from '../../utils/localizedDisplay';

type Nav = StackNavigationProp<RootStackParamList, 'UnpaidBills'>;

const UnpaidBillsScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const [items, setItems] = React.useState<UnpaidCharge[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUnpaidCharges();
      setItems(data);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onPay = async (sessionId: string) => {
    try {
      await payUnpaidCharge(sessionId);
      dispatch(fetchWalletBalance());
      await load();
      Alert.alert(t.common.success, t.wallet.payOk);
    } catch {
      Alert.alert(t.wallet.payFail, t.common.retry);
    }
  };

  return (
    <Screen>
      <ScreenHeader title={t.wallet.unpaidTitle} onBack={() => navigation.goBack()} />

      {loading ? (
        <Text style={styles.empty}>{t.common.loading}</Text>
      ) : items.length === 0 ? (
        <Text style={styles.empty}>{t.wallet.unpaidEmpty}</Text>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => String(item.session_id)}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{t.wallet.unpaidCharge}</Text>
              <Text style={styles.cardSub}>
                {item.charge_point_name || publicChargerIdentity(item, t.common.unknown)}
              </Text>
              <Text style={styles.amount}>{formatMoneyCOP(item.amount)}</Text>
              <Button title={t.wallet.payNow} onPress={() => onPay(item.session_id)} size="small" />
            </View>
          )}
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  empty: { textAlign: 'center', marginTop: 48, color: COLORS.TEXT_SECONDARY },
  list: { padding: 16, gap: 12 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  cardTitle: { fontSize: 16, fontWeight: '600', color: COLORS.TEXT_PRIMARY },
  cardSub: { fontSize: 13, color: COLORS.TEXT_SECONDARY, marginTop: 4 },
  amount: { fontSize: 20, fontWeight: '700', color: COLORS.PRIMARY, marginVertical: 12 },
});

export default UnpaidBillsScreen;
