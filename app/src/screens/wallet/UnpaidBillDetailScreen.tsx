/** PAY-MP-002 typed unpaid invoice detail and recovery actions. */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Linking, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import { createIdempotencyKey, isServerCheckoutUrl } from '../../api/payments';
import { trackCheckoutSession } from '../../features/payment/checkoutCoordinator';
import { createRecoveryAttempt, createSupportCase, getUnpaidInvoice } from '../../features/payMp002/adapter';
import type { RecoveryMethod, RecoveryMethodOption, UnpaidInvoiceDetail } from '../../features/payMp002/types';
import type { RootStackParamList } from '../../types';

type Route = RouteProp<RootStackParamList, 'UnpaidBillDetail'>;
type Nav = StackNavigationProp<RootStackParamList, 'UnpaidBillDetail'>;

const displayAmount = (value: string): string => {
  const match = value.trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return value;
  const [, sign, integer, fraction = ''] = match;
  const groupedInteger = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const decimal = fraction ? `,${fraction}` : '';
  return `${sign}$${groupedInteger}${decimal} COP`;
};

const UnpaidBillDetailScreen = () => {
  const { t } = useI18n();
  const route = useRoute<Route>();
  const navigation = useNavigation<Nav>();
  const [detail, setDetail] = useState<UnpaidInvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [recovering, setRecovering] = useState<RecoveryMethod | null>(null);
  const [supporting, setSupporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      setDetail(await getUnpaidInvoice(route.params.invoiceId));
    } catch {
      setDetail(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [route.params.invoiceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const recover = useCallback(async (option: RecoveryMethodOption) => {
    if (!option.enabled || recovering) return;
    setRecovering(option.method);
    try {
      const attempt = await createRecoveryAttempt(
        route.params.invoiceId,
        option.method,
        createIdempotencyKey(),
        option.saved_payment_method_ref?.id ?? null,
      );
      if (attempt.status === 'allocated' && attempt.allocation?.status === 'confirmed') {
        Alert.alert(t.common.success, t.wallet.payOk, [
          { text: t.common.success, onPress: () => navigation.goBack() },
        ]);
        return;
      }
      if (attempt.next_action.type === 'open_checkout' && attempt.next_action.checkout_session_id) {
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
        return;
      }
      Alert.alert(t.wallet.payFail, t.wallet.recoveryUnavailable);
    } catch {
      Alert.alert(t.wallet.payFail, t.common.retry);
    } finally {
      setRecovering(null);
    }
  }, [navigation, recovering, route.params.invoiceId, t]);

  const openSupport = useCallback(async () => {
    if (!detail || supporting || !detail.allowed_actions.includes('contact_support')) return;
    setSupporting(true);
    try {
      const supportCase = await createSupportCase({
        category: 'payment_recovery',
        resource_type: 'invoice',
        resource_id: detail.invoice_id,
      });
      Alert.alert(t.common.success, t.history.supportCreated, [
        { text: t.common.success, onPress: () => navigation.navigate('SupportCaseDetail', { caseId: supportCase.case_id }) },
      ]);
    } catch {
      Alert.alert(t.history.supportCreateFailed);
    } finally {
      setSupporting(false);
    }
  }, [detail, navigation, supporting, t]);

  return (
    <Screen>
      <ScreenHeader title={t.wallet.viewDetails} onBack={() => navigation.goBack()} />
      {loading ? (
        <Text style={styles.center}>{t.common.loading}</Text>
      ) : failed || !detail ? (
        <View style={styles.centerBlock}>
          <Text style={styles.center}>{t.wallet.loadFailed}</Text>
          <Button title={t.common.retry} onPress={() => void load()} variant="outline" size="small" />
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <Card style={styles.card}>
            <Text style={styles.title}>{t.wallet.unpaidCharge}</Text>
            <Text style={styles.reference}>{t.wallet.invoiceReference}: {detail.invoice_reference}</Text>
            <Text style={styles.amount}>{displayAmount(detail.outstanding_amount)}</Text>
            <Text style={styles.label}>{t.wallet.amountDue}</Text>
            <Text style={styles.value}>{detail.currency}</Text>
            <Text style={styles.label}>{t.wallet.energyConsumed}</Text>
            <Text style={styles.value}>{detail.energy_kwh} kWh</Text>
            <Text style={styles.label}>{t.wallet.paymentMethod}</Text>
            <Text style={styles.value}>{detail.blocking_reason}</Text>
          </Card>

          <Card style={styles.card}>
            <Text style={styles.sectionTitle}>{t.wallet.paymentMethod}</Text>
            {detail.available_methods.map((option) => {
              const label = option.method === 'wallet'
                ? t.wallet.payWithWallet
                : option.method === 'new_card'
                  ? t.wallet.payWithNewCard
                  : `${t.wallet.savedCard} · ${option.saved_payment_method_ref?.brand ?? ''} •••• ${option.saved_payment_method_ref?.last_four ?? ''}`;
              return (
                <Button
                  key={`${option.method}-${option.saved_payment_method_ref?.id ?? 'wallet'}`}
                  title={label}
                  onPress={() => void recover(option)}
                  variant={option.enabled ? 'primary' : 'outline'}
                  disabled={!option.enabled || recovering !== null}
                  loading={recovering === option.method}
                  style={styles.action}
                />
              );
            })}
            {detail.available_methods.length === 0 && (
              <Text style={styles.center}>{t.wallet.paymentMethodUnavailable}</Text>
            )}
          </Card>

          {detail.allowed_actions.includes('contact_support') && (
            <Button
              testID="app-unpaid-contact-support"
              title={t.history.contactSupport}
              onPress={() => void openSupport()}
              variant="outline"
              loading={supporting}
              disabled={supporting || recovering !== null}
              style={styles.action}
            />
          )}
        </ScrollView>
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  card: { padding: 16 },
  title: { fontSize: 20, fontWeight: '700', color: COLORS.TEXT_PRIMARY },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: COLORS.TEXT_PRIMARY, marginBottom: 8 },
  reference: { color: COLORS.TEXT_SECONDARY, marginTop: 6 },
  amount: { fontSize: 28, fontWeight: '800', color: COLORS.PRIMARY, marginTop: 20 },
  label: { fontSize: 12, color: COLORS.TEXT_SECONDARY, marginTop: 16 },
  value: { fontSize: 15, color: COLORS.TEXT_PRIMARY, marginTop: 4 },
  action: { marginTop: 8 },
  centerBlock: { alignItems: 'center', marginTop: 48, paddingHorizontal: 16 },
  center: { textAlign: 'center', marginTop: 48, color: COLORS.TEXT_SECONDARY },
});

export default UnpaidBillDetailScreen;
