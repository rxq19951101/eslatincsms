/** Compatibility route: all Mercado Pago card entry stays on the hosted page. */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Linking, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import {
  formatWalletTopUpAmount,
  isServerCheckoutUrl,
} from '../../api/payments';
import { startCheckoutSession } from '../../features/payment/checkoutCoordinator';
import { useI18n } from '../../i18n';
import Button from '../../components/ui/Button';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';

type MercadoPagoPaymentRouteProp = RouteProp<RootStackParamList, 'MercadoPagoPayment'>;
type MercadoPagoNav = StackNavigationProp<RootStackParamList, 'MercadoPagoPayment'>;

const MercadoPagoPaymentScreen = () => {
  const { t } = useI18n();
  const navigation = useNavigation<MercadoPagoNav>();
  const route = useRoute<MercadoPagoPaymentRouteProp>();
  const { amount, type } = route.params || {};
  const [opening, setOpening] = useState(false);
  const autoStarted = useRef(false);

  const openHostedCheckout = useCallback(async () => {
    if (opening || !amount || type !== 'top_up') return;
    setOpening(true);
    try {
      const session = await startCheckoutSession({
        purpose: 'wallet_top_up',
        payment_method_mode: 'new_card',
        save_card: false,
        amount: formatWalletTopUpAmount(amount),
        currency: 'COP',
      });
      if (!isServerCheckoutUrl(session.checkout_url)) throw new Error('invalid_checkout_url');
      await Linking.openURL(session.checkout_url);
    } catch {
      Alert.alert(t.common.error, t.payment.openFailed);
    } finally {
      setOpening(false);
    }
  }, [amount, opening, t.common.error, t.payment.openFailed, type]);

  useEffect(() => {
    if (autoStarted.current) return;
    autoStarted.current = true;
    void openHostedCheckout();
  }, [openHostedCheckout]);

  const unsupported = type !== 'top_up' || !amount;

  return (
    <Screen>
      <ScreenHeader title={t.payment.title} onBack={() => navigation.goBack()} />
      <View style={styles.content}>
        <Text style={styles.title}>{unsupported ? t.payment.invalidLink : t.payment.opening}</Text>
        <Text style={styles.message}>
          {unsupported ? t.payment.resultUnknownBody : t.payment.openBrowser}
        </Text>
        {!unsupported && (
          <Button
            title={opening ? t.payment.opening : t.payment.continueToSecurePage}
            onPress={() => void openHostedCheckout()}
            loading={opening}
            disabled={opening}
            style={styles.button}
          />
        )}
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: IOS_STYLES.SPACING.XL },
  title: { fontSize: IOS_STYLES.FONT_SIZE.TITLE, fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD, color: COLORS.TEXT_PRIMARY, textAlign: 'center', marginBottom: IOS_STYLES.SPACING.SM },
  message: { fontSize: IOS_STYLES.FONT_SIZE.BODY, color: COLORS.TEXT_SECONDARY, textAlign: 'center', lineHeight: 24, marginBottom: IOS_STYLES.SPACING.XL },
  button: { width: '100%' },
});

export default MercadoPagoPaymentScreen;
