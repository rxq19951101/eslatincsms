/** PAY-MP-002 unpaid invoice list and recovery entry. */
import React, { useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Alert, Linking } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList } from '../../types';
import Button from '../../components/ui/Button';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import {
  createRecoveryAttempt,
  getUnpaidInvoice,
  getUnpaidInvoices,
} from '../../features/payMp002/adapter';
import { createIdempotencyKey, isServerCheckoutUrl } from '../../api/payments';
import { trackCheckoutSession } from '../../features/payment/checkoutCoordinator';
import type {
  RecoveryMethod,
  RecoveryMethodOption,
  UnpaidInvoiceProjection,
} from '../../features/payMp002/types';
import { formatMoneyCOP } from '../../utils/formatMoney';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import { useAppDispatch } from '../../hooks/useRedux';

type Nav = StackNavigationProp<RootStackParamList, 'UnpaidBills'>;

function displayAmount(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? formatMoneyCOP(amount) : value;
}

const UnpaidBillsScreen = () => {
  const { t } = useI18n();
  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const [items, setItems] = React.useState<UnpaidInvoiceProjection[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState(false);
  const [recoveringInvoiceId, setRecoveringInvoiceId] = React.useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const page = await getUnpaidInvoices({ limit: 50 });
      setItems(page.items);
    } catch {
      setItems([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const startRecovery = useCallback(async (
    invoiceId: string,
    method: RecoveryMethod,
    savedPaymentMethodId: string | null,
  ) => {
    setRecoveringInvoiceId(invoiceId);
    try {
      const attempt = await createRecoveryAttempt(
        invoiceId,
        method,
        createIdempotencyKey(),
        savedPaymentMethodId,
      );
      if (attempt.status === 'allocated' && attempt.allocation?.status === 'confirmed') {
        dispatch(fetchWalletBalance());
        await load();
        Alert.alert(t.common.success, t.wallet.payOk);
      } else if (attempt.next_action.type === 'open_checkout' && attempt.next_action.checkout_session_id) {
        if (attempt.next_action.url && isServerCheckoutUrl(attempt.next_action.url)) {
          if (attempt.next_action.expires_at) {
            await trackCheckoutSession({
              checkout_session_id: attempt.next_action.checkout_session_id,
              purpose: 'unpaid_charge',
              expires_at: attempt.next_action.expires_at,
            });
          }
          await Linking.openURL(attempt.next_action.url);
        } else {
          navigation.navigate('PaymentResult', {
            checkout_session_id: attempt.next_action.checkout_session_id,
          });
        }
      } else {
        Alert.alert(t.wallet.payFail, t.payMp002.recovery);
      }
    } catch {
      // Provider-specific errors stay behind the typed recovery boundary.
      Alert.alert(t.wallet.payFail, t.common.retry);
    } finally {
      setRecoveringInvoiceId(null);
    }
  }, [dispatch, load, navigation, t]);

  const onPay = useCallback(async (invoiceId: string) => {
    if (recoveringInvoiceId) return;
    setRecoveringInvoiceId(invoiceId);
    try {
      const detail = await getUnpaidInvoice(invoiceId);
      const enabledMethods = detail.available_methods.filter((method) => method.enabled);
      if (enabledMethods.length === 0) {
        Alert.alert(t.wallet.payFail, t.wallet.paymentMethodUnavailable);
        return;
      }
      const buttons = enabledMethods.map((option: RecoveryMethodOption) => ({
        text: option.method === 'wallet'
          ? t.wallet.payWithWallet
          : option.method === 'new_card'
            ? t.wallet.payWithNewCard
            : `${t.wallet.savedCard} · ${option.saved_payment_method_ref?.brand ?? ''} •••• ${option.saved_payment_method_ref?.last_four ?? ''}`,
        onPress: () => {
          void startRecovery(
            invoiceId,
            option.method,
            option.saved_payment_method_ref?.id ?? null,
          );
        },
      }));
      Alert.alert(t.wallet.paymentMethod, t.wallet.unpaidCharge, [
        ...buttons,
        { text: t.common.cancel, style: 'cancel' },
      ]);
    } catch {
      Alert.alert(t.wallet.payFail, t.common.retry);
    } finally {
      // The actual recovery callback owns the busy state after a method is chosen.
      setRecoveringInvoiceId(null);
    }
  }, [recoveringInvoiceId, startRecovery, t]);

  const renderItem = ({ item }: { item: UnpaidInvoiceProjection }) => (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{t.wallet.unpaidCharge}</Text>
      <Text style={styles.cardSub}>
        {item.charge_point_reference || item.site || item.invoice_reference}
      </Text>
      <Text style={styles.amount}>{displayAmount(item.outstanding_amount)}</Text>
      <Button
        title={t.wallet.payNow}
        onPress={() => void onPay(item.invoice_id)}
        size="small"
        loading={recoveringInvoiceId === item.invoice_id}
        disabled={Boolean(recoveringInvoiceId)}
      />
      <Button
        title={t.wallet.viewDetails}
        onPress={() => navigation.navigate('UnpaidBillDetail', { invoiceId: item.invoice_id })}
        size="small"
        variant="outline"
        disabled={Boolean(recoveringInvoiceId)}
        style={styles.detailsButton}
      />
    </View>
  );

  return (
    <Screen>
      <ScreenHeader title={t.wallet.unpaidTitle} onBack={() => navigation.goBack()} />

      {loading ? (
        <Text style={styles.empty}>{t.common.loading}</Text>
      ) : loadError ? (
        <View style={styles.errorState}>
          <Text style={styles.empty}>{t.wallet.loadFailed}</Text>
          <Button title={t.common.retry} onPress={() => void load()} variant="outline" size="small" />
        </View>
      ) : items.length === 0 ? (
        <Text style={styles.empty}>{t.wallet.unpaidEmpty}</Text>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.invoice_id}
          contentContainerStyle={styles.list}
          renderItem={renderItem}
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  empty: { textAlign: 'center', marginTop: 48, color: COLORS.TEXT_SECONDARY },
  errorState: { alignItems: 'center', marginTop: 48, paddingHorizontal: 16 },
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
  detailsButton: { marginTop: 8 },
});

export default UnpaidBillsScreen;
