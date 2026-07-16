/**
 * 支付方式管理（简化版，使用本地存储）
 */

import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList, PaymentMethod } from '../../types';
import { deletePaymentMethod, getPaymentMethods, setDefaultPaymentMethod } from '../../utils/paymentMethodsStorage';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Badge from '../../components/ui/Badge';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';

type Nav = StackNavigationProp<RootStackParamList, 'PaymentMethods'>;

const PaymentMethodsScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setMethods(await getPaymentMethods());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [])
  );

  const onDelete = (id: string) => {
    Alert.alert(t.payment.deleteTitle, t.payment.deleteConfirm, [
      { text: t.common.cancel, style: 'cancel' },
      {
        text: t.common.delete,
        style: 'destructive',
        onPress: async () => setMethods(await deletePaymentMethod(id)),
      },
    ]);
  };

  const onSetDefault = async (id: string) => {
    setMethods(await setDefaultPaymentMethod(id));
  };

  const renderItem = ({ item }: { item: PaymentMethod }) => {
    const label = item.type.toUpperCase();
    const suffix = item.last_four ? `**** ${item.last_four}` : '';
    return (
      <TouchableOpacity style={styles.card} onPress={() => onSetDefault(item.id)} disabled={loading}>
        <View style={styles.left}>
          <Text style={styles.title}>
            {label} {suffix}
          </Text>
          <Text style={styles.subTitle}>{item.is_default ? t.payment.default : t.payment.setDefault}</Text>
        </View>
        <View style={styles.right}>
          {item.is_default && <Badge label={t.payment.default} variant="success" style={styles.badge} />}
          <TouchableOpacity style={styles.deleteBtn} onPress={() => onDelete(item.id)}>
            <Text style={styles.deleteText}>{t.common.delete}</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Screen>
      <ScreenHeader
        title={t.payment.methodsDemo}
        onBack={() => navigation.goBack()}
        right={
          <TouchableOpacity style={styles.addBtn} onPress={() => navigation.navigate('AddPayment')}>
            <Text style={styles.addText}>{t.payment.add}</Text>
          </TouchableOpacity>
        }
      />

      <View style={styles.demoBanner}>
        <Text style={styles.demoBannerText}>
          {t.payment.demoHint}
        </Text>
      </View>

      {methods.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.centerText}>{loading ? t.common.loading : t.payment.empty}</Text>
          <Button title={t.payment.addMethod} onPress={() => navigation.navigate('AddPayment')} style={styles.primaryBtn} />
        </View>
      ) : (
        <FlatList
          data={methods}
          keyExtractor={(it) => it.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 24 }}
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  addBtn: { minWidth: 44, height: 44, alignItems: 'flex-end', justifyContent: 'center', paddingLeft: 8 },
  addText: { color: COLORS.PRIMARY, fontWeight: '900' },
  demoBanner: {
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 12,
    backgroundColor: '#FFFBEB',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FDE68A',
  },
  demoBannerText: { fontSize: 13, color: COLORS.TEXT_PRIMARY, lineHeight: 20 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  centerText: { color: COLORS.TEXT_SECONDARY },
  primaryBtn: { marginTop: 16 },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    marginBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  left: { flex: 1, paddingRight: 10 },
  title: { fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  right: { alignItems: 'flex-end' },
  badge: { marginBottom: 6 },
  deleteBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: '#FEE2E2' },
  deleteText: { color: COLORS.ERROR, fontWeight: '900', fontSize: 12 },
});

export default PaymentMethodsScreen;
