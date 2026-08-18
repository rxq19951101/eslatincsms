/** PAY-MP-001 canonical payment-method management. */

import React, { useCallback, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList, CanonicalPaymentMethod } from '../../types';
import {
  deletePaymentMethodRemote,
  getPaymentMethodTypeLabelKey,
  listPaymentMethods,
  setPaymentMethodDefault,
} from '../../api/payments';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Badge from '../../components/ui/Badge';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';

type Nav = StackNavigationProp<RootStackParamList, 'PaymentMethods'>;

const PaymentMethodsScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const [methods, setMethods] = useState<CanonicalPaymentMethod[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      setMethods(await listPaymentMethods());
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const onDelete = (id: string) => {
    Alert.alert(t.payment.deleteTitle, t.payment.deleteConfirm, [
      { text: t.common.cancel, style: 'cancel' },
      {
        text: t.common.delete,
        style: 'destructive',
        onPress: () => {
          void (async () => {
            setPendingId(id);
            try {
              await deletePaymentMethodRemote(id);
              await load();
            } catch {
              Alert.alert(t.common.error, t.payment.deleteFailed);
            } finally {
              setPendingId(null);
            }
          })();
        },
      },
    ]);
  };

  const onSetDefault = async (id: string) => {
    if (pendingId) return;
    setPendingId(id);
    try {
      await setPaymentMethodDefault(id);
      await load();
    } catch {
      Alert.alert(t.common.error, t.payment.defaultFailed);
    } finally {
      setPendingId(null);
    }
  };

  const renderItem = ({ item }: { item: CanonicalPaymentMethod }) => {
    const brand = item.brand?.trim() || t.payment.unknownBrand;
    const paymentType = t.payment[getPaymentMethodTypeLabelKey(item.payment_type)];
    const suffix = item.last_four ? `•••• ${item.last_four}` : '';
    const isPending = pendingId === item.id;
    return (
      <View style={styles.card}>
        <View style={styles.left} accessibilityLabel={`${brand} ${suffix}. ${paymentType}${item.is_default ? `. ${t.payment.default}` : ''}`}>
          <Text style={styles.title}>{brand} {suffix}</Text>
          <Text style={styles.subTitle}>{item.provider} · {paymentType}</Text>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel={item.is_default ? t.payment.default : t.payment.setDefault}
            onPress={() => void onSetDefault(item.id)}
            disabled={status === 'loading' || Boolean(pendingId) || item.is_default}
            style={styles.defaultAction}
          >
            <Text style={styles.defaultActionText}>
              {item.is_default ? t.payment.default : t.payment.setDefault}
            </Text>
          </TouchableOpacity>
        </View>
        <View style={styles.right}>
          {item.is_default && <Badge label={t.payment.default} variant="success" style={styles.badge} />}
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel={t.payment.deleteTitle}
            style={[styles.deleteBtn, isPending && styles.disabledAction]}
            onPress={() => onDelete(item.id)}
            disabled={Boolean(pendingId)}
          >
            <Text style={styles.deleteText}>{t.common.delete}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <Screen>
      <ScreenHeader
        title={t.payment.methods}
        onBack={() => navigation.goBack()}
        right={
          <TouchableOpacity style={styles.addBtn} onPress={() => navigation.navigate('AddPayment')}>
            <Text style={styles.addText}>{t.payment.add}</Text>
          </TouchableOpacity>
        }
      />

      {status === 'error' ? (
        <View accessibilityRole="alert" style={styles.center}>
          <Text style={styles.centerText}>{t.payment.loadFailed}</Text>
          <Button title={t.common.retry} onPress={() => void load()} style={styles.primaryBtn} />
        </View>
      ) : status === 'loading' || status === 'idle' ? (
        <View style={styles.center}>
          <Text style={styles.centerText}>{t.common.loading}</Text>
        </View>
      ) : methods.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.centerText}>{t.payment.empty}</Text>
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
  defaultAction: { marginTop: 8, alignSelf: 'flex-start' },
  defaultActionText: { color: COLORS.PRIMARY, fontSize: 12, fontWeight: '800' },
  right: { alignItems: 'flex-end' },
  badge: { marginBottom: 6 },
  deleteBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: '#FEE2E2' },
  disabledAction: { opacity: 0.5 },
  deleteText: { color: COLORS.ERROR, fontWeight: '900', fontSize: 12 },
});

export default PaymentMethodsScreen;
