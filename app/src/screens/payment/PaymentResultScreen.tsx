/** Shared hosted-checkout result and recovery screen. */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import type { CheckoutSessionResponse, RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { useAppDispatch } from '../../hooks/useRedux';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import { useI18n } from '../../i18n';
import {
  isAllowedMercadoPagoActionUrl,
} from '../../api/payments';
import {
  clearPendingCheckoutSession,
  isCheckoutTerminal,
  resolveCheckoutSession,
  type CheckoutRecoveryResult,
} from '../../features/payment/checkoutCoordinator';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';

type PaymentResultRouteProp = RouteProp<RootStackParamList, 'PaymentResult'>;
type PaymentResultNavProp = StackNavigationProp<RootStackParamList, 'PaymentResult'>;

const PaymentResultScreen = () => {
  const { t } = useI18n();
  const navigation = useNavigation<PaymentResultNavProp>();
  const route = useRoute<PaymentResultRouteProp>();
  const dispatch = useAppDispatch();
  const { status: legacyStatus, checkout_session_id: checkoutSessionId } = route.params || {};
  const [session, setSession] = useState<CheckoutSessionResponse | null>(null);
  const [recovery, setRecovery] = useState<CheckoutRecoveryResult | null>(null);
  const [loading, setLoading] = useState(Boolean(checkoutSessionId));
  const [failed, setFailed] = useState(false);
  const pollAttempts = useRef(0);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSession = useCallback(async (resetAttempts = false) => {
    if (!checkoutSessionId) return;
    if (resetAttempts) pollAttempts.current = 0;
    setLoading(true);
    setFailed(false);
    try {
      const next = await resolveCheckoutSession(checkoutSessionId);
      setRecovery(next);
      if (next.kind === 'resolved' && next.session) {
        setSession(next.session);
      } else if (next.kind === 'expired_or_missing') {
        setSession(null);
      }
      if (next.session?.status === 'approved' && next.session.purpose === 'wallet_top_up') {
        dispatch(fetchWalletBalance());
      }
    } catch {
      setFailed(true);
      setRecovery({ kind: 'network_unknown', session: null });
    } finally {
      setLoading(false);
    }
  }, [checkoutSessionId, dispatch]);

  useEffect(() => {
    if (!checkoutSessionId) return;
    void loadSession(true);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [checkoutSessionId, loadSession]);

  useEffect(() => {
    if (recovery?.kind !== 'resolved' || !session ||
        isCheckoutTerminal(session.status) || session.status === 'action_required') return;
    if (pollAttempts.current >= 10) return;
    pollAttempts.current += 1;
    pollTimer.current = setTimeout(() => void loadSession(), 4000);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [loadSession, recovery?.kind, session]);

  useEffect(() => {
    if (!checkoutSessionId) return;
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'active') void loadSession(true);
    });
    return () => subscription.remove();
  }, [checkoutSessionId, loadSession]);

  const effectiveStatus = session?.status ?? (checkoutSessionId ? undefined : legacyStatus);
  const recoveryKind = recovery?.kind;
  const purpose = session?.purpose ?? recovery?.purpose;
  const isExpired = recoveryKind === 'expired_or_missing' || session?.status === 'expired';
  const actionUrl = session?.status === 'action_required' && session.next_action?.type === 'open_url'
    && isAllowedMercadoPagoActionUrl(session.next_action.url)
    ? session.next_action.url
    : null;

  const getStatusConfig = () => {
    if (recoveryKind === 'expired_or_missing') {
      return { title: t.payment.checkoutExpiredTitle, message: t.payment.checkoutExpiredBody, variant: 'warning' as const };
    }
    if (recoveryKind === 'already_submitted') {
      return { title: t.payment.checkoutSubmittedTitle, message: t.payment.checkoutSubmittedBody, variant: 'info' as const };
    }
    if (recoveryKind === 'temporarily_unavailable') {
      return { title: t.payment.checkoutUnavailableTitle, message: t.payment.checkoutUnavailableBody, variant: 'warning' as const };
    }
    if (recoveryKind === 'network_unknown') {
      return { title: t.payment.checkoutNetworkUnknownTitle, message: t.payment.checkoutNetworkUnknownBody, variant: 'neutral' as const };
    }
    switch (effectiveStatus) {
      case 'approved':
        return { title: t.payment.resultOkTitle, message: t.payment.resultOkBody, variant: 'success' as const };
      case 'processing':
        return { title: t.payment.resultProcessingTitle, message: t.payment.resultProcessingBody, variant: 'warning' as const };
      case 'action_required':
        return { title: t.payment.resultActionRequiredTitle, message: t.payment.resultActionRequiredBody, variant: 'warning' as const };
      case 'created':
      case 'ready':
        return { title: t.payment.resultPendingTitle, message: t.payment.resultPendingBody, variant: 'info' as const };
      case 'declined':
        return { title: t.payment.resultDeniedTitle, message: t.payment.resultDeniedBody, variant: 'error' as const };
      case 'expired':
        return { title: t.payment.resultExpiredTitle, message: t.payment.resultExpiredBody, variant: 'warning' as const };
      case 'voided':
      case 'refunded':
      case 'error':
        return { title: t.payment.resultErrorTitle, message: t.payment.resultErrorBody, variant: 'error' as const };
      default:
        return { title: t.payment.resultUnknownTitle, message: t.payment.resultUnknownBody, variant: 'neutral' as const };
    }
  };

  const config = getStatusConfig();

  const openAction = async () => {
    if (!actionUrl) return;
    await Linking.openURL(actionUrl);
  };

  const handleDone = () => {
    if (session && isCheckoutTerminal(session.status)) {
      void clearPendingCheckoutSession();
    }
    if (session?.purpose === 'wallet_top_up' || (!session && effectiveStatus === 'approved')) {
      navigation.navigate('MainTabs', { screen: 'MyWallet' });
      return;
    }
    if (session?.purpose === 'save_card') {
      navigation.navigate('PaymentMethods');
      return;
    }
    if (session?.purpose === 'unpaid_charge') {
      navigation.navigate('UnpaidBills');
      return;
    }
    navigation.goBack();
  };

  const handleRestart = () => {
    if (purpose === 'save_card') {
      navigation.navigate('AddPayment');
      return;
    }
    if (purpose === 'wallet_top_up') {
      navigation.navigate('PaymentHub');
      return;
    }
    navigation.goBack();
  };

  const refresh = () => {
    if (checkoutSessionId) {
      void loadSession(true);
      return;
    }
  };

  const canRetryCheckout = Boolean(checkoutSessionId) && (
    recoveryKind === 'already_submitted' ||
    recoveryKind === 'temporarily_unavailable' ||
    recoveryKind === 'network_unknown' ||
    Boolean(session && !isCheckoutTerminal(session.status))
  );

  return (
    <Screen>
      <ScreenHeader title={t.payment.title} onBack={() => navigation.goBack()} />
      <SafeAreaView style={styles.container} edges={['bottom']}>
        <View style={styles.content}>
          {loading && !session ? (
            <Text style={styles.message}>{t.payment.processing}</Text>
          ) : (
            <>
              <Badge label={config.title} variant={config.variant} />
              <Text style={styles.title}>{config.title}</Text>
              <Text
                testID={recoveryKind ? `app-checkout-recovery-${recoveryKind}` : undefined}
                accessibilityRole={failed || recoveryKind === 'expired_or_missing' ||
                  recoveryKind === 'temporarily_unavailable' || recoveryKind === 'network_unknown'
                  ? 'alert'
                  : undefined}
                accessibilityLiveRegion="polite"
                style={styles.message}
              >
                {failed ? t.payment.resultCheckFailed : config.message}
              </Text>
              {session?.payment_order_id && (
                <View style={styles.reference}>
                  <Text style={styles.referenceLabel}>{t.payment.orderId}</Text>
                  <Text style={styles.referenceValue}>{session.payment_order_id}</Text>
                </View>
              )}
            </>
          )}
        </View>

        <View style={styles.footer}>
          {actionUrl && (
            <Button title={t.payment.open3ds} onPress={() => void openAction()} style={styles.button} />
          )}
          {isExpired && (
            <Button
              testID="app-checkout-restart"
              title={t.payment.restartCheckout}
              variant="outline"
              onPress={handleRestart}
              style={styles.button}
            />
          )}
          {(failed || canRetryCheckout) && !isExpired && (
            <Button
              testID="app-checkout-refresh"
              title={t.payment.refreshStatus}
              variant="outline"
              onPress={refresh}
              loading={loading}
              disabled={loading}
              style={styles.button}
            />
          )}
          <Button
            title={effectiveStatus === 'approved' ? t.payment.done : t.common.back}
            variant={effectiveStatus === 'approved' ? 'primary' : 'text'}
            onPress={handleDone}
            style={styles.button}
          />
        </View>
      </SafeAreaView>
    </Screen>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: IOS_STYLES.SPACING.XL },
  title: { fontSize: IOS_STYLES.FONT_SIZE.TITLE, fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD, color: COLORS.TEXT_PRIMARY, marginTop: IOS_STYLES.SPACING.LG, marginBottom: IOS_STYLES.SPACING.SM },
  message: { fontSize: IOS_STYLES.FONT_SIZE.BODY, color: COLORS.TEXT_SECONDARY, textAlign: 'center', marginBottom: IOS_STYLES.SPACING.XL },
  reference: { marginTop: IOS_STYLES.SPACING.LG, padding: IOS_STYLES.SPACING.MD, backgroundColor: COLORS.CARD_BG, borderRadius: IOS_STYLES.RADIUS.MEDIUM, alignItems: 'center' },
  referenceLabel: { fontSize: IOS_STYLES.FONT_SIZE.SMALL, color: COLORS.TEXT_SECONDARY, marginBottom: IOS_STYLES.SPACING.XS },
  referenceValue: { fontSize: IOS_STYLES.FONT_SIZE.BODY, fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD, color: COLORS.TEXT_PRIMARY },
  footer: { padding: IOS_STYLES.SPACING.MD, borderTopWidth: 1, borderTopColor: COLORS.BORDER },
  button: { width: '100%', marginBottom: IOS_STYLES.SPACING.SM },
});

export default PaymentResultScreen;
