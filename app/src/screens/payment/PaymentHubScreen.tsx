/**
 * 支付中枢：支付轨关闭时仅展示余额说明；开启后显示充值入口。
 */
import React, { useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS, IOS_STYLES, PAYMENT_RAILS_ENABLED, LEGAL_URLS } from '../../constants/config';
import type { RootStackParamList } from '../../types';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import { formatMoneyCOP } from '../../utils/formatMoney';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import ListItem from '../../components/ui/ListItem';
import { createWompiPayment } from '../../api/payments';
import { useI18n } from '../../i18n';

type Nav = StackNavigationProp<RootStackParamList, 'PaymentHub'>;

const TOP_UP_AMOUNTS = [10000, 20000, 50000];

const PaymentHubScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const dispatch = useAppDispatch();
  const { balance, loadingBalance } = useAppSelector((s) => s.wallet);

  useEffect(() => {
    dispatch(fetchWalletBalance());
  }, [dispatch]);

  useFocusEffect(
    useCallback(() => {
      dispatch(fetchWalletBalance());
    }, [dispatch])
  );

  const bal = balance?.balance ?? 0;

  const topUpWompi = async (amount: number) => {
    try {
      const res = await createWompiPayment({ amount, type: 'top_up', currency: 'COP' });
      navigation.navigate('WompiPayment', {
        orderId: res.order_id,
        checkoutUrl: res.checkout_url,
        amount,
      });
    } catch (e: any) {
      alert(e?.message || t.payment.createFailed);
    }
  };

  return (
    <Screen>
      <ScreenHeader title="Pagos y billetera" onBack={() => navigation.goBack()} />

      <ScrollView contentContainerStyle={styles.scroll}>
        <Card style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Saldo disponible</Text>
          <Text style={styles.balanceAmount}>
            {loadingBalance && balance == null ? '—' : formatMoneyCOP(bal)}
          </Text>
          <Text style={styles.balanceHint}>
            {PAYMENT_RAILS_ENABLED
              ? 'Montos en pesos colombianos (COP). Recargas procesadas de forma segura con Mercado Pago o Wompi.'
              : 'Montos en COP. El pago en la app aún no está disponible; el saldo lo asigna el operador.'}
          </Text>
        </Card>

        {!PAYMENT_RAILS_ENABLED && (
          <View style={styles.demoBanner}>
            <Text style={styles.demoText}>
              Contacte al operador o escriba a {LEGAL_URLS.supportEmail} para solicitar saldo. El cobro
              de la carga se descuenta de la billetera al finalizar.
            </Text>
          </View>
        )}

        {PAYMENT_RAILS_ENABLED && (
          <>
            <Text style={styles.sectionTitle}>Recargar saldo</Text>
            <View style={styles.chips}>
              {TOP_UP_AMOUNTS.map((amt) => (
                <Button
                  key={amt}
                  title={`+ ${formatMoneyCOP(amt, { decimals: 0 })}`}
                  onPress={() =>
                    navigation.navigate('MercadoPagoPayment', {
                      amount: amt,
                      type: 'top_up',
                    })
                  }
                  variant="secondary"
                  size="small"
                  style={styles.chip}
                />
              ))}
            </View>

            <Text style={styles.sectionTitle}>Recarga con Wompi</Text>
            <View style={styles.chips}>
              {TOP_UP_AMOUNTS.map((amt) => (
                <Button
                  key={`wompi-${amt}`}
                  title={`Wompi ${formatMoneyCOP(amt, { decimals: 0 })}`}
                  onPress={() => topUpWompi(amt)}
                  variant="secondary"
                  size="small"
                  style={styles.chip}
                />
              ))}
            </View>

            <View style={styles.demoBanner}>
              <Text style={styles.demoText}>{t.payment.demoNote}</Text>
            </View>

            <ListItem label="Administrar métodos de pago" onPress={() => navigation.navigate('PaymentMethods')} />
          </>
        )}

        <View style={styles.links}>
          <ListItem label="Facturas pendientes" onPress={() => navigation.navigate('UnpaidBills')} />
          <ListItem label="Ver movimientos de billetera" onPress={() => navigation.navigate('MainTabs', { screen: 'MyWallet' })} />
        </View>
      </ScrollView>
    </Screen>
  );
};

const styles = StyleSheet.create({
  scroll: { padding: IOS_STYLES.SPACING.MD, paddingBottom: 40 },
  balanceCard: {
    padding: IOS_STYLES.SPACING.LG,
    backgroundColor: COLORS.PRIMARY,
    marginBottom: IOS_STYLES.SPACING.LG,
    borderRadius: IOS_STYLES.RADIUS.LARGE,
  },
  balanceLabel: { fontSize: 14, color: '#fff', opacity: 0.85 },
  balanceAmount: { fontSize: 28, fontWeight: '800', color: '#fff', marginVertical: 8 },
  balanceHint: { fontSize: 12, color: '#fff', opacity: 0.85, lineHeight: 18 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: IOS_STYLES.SPACING.SM,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: IOS_STYLES.SPACING.LG },
  chip: { marginRight: 8, marginBottom: 8 },
  links: { overflow: 'hidden', borderRadius: IOS_STYLES.RADIUS.LARGE, borderWidth: 1, borderColor: COLORS.BORDER },
  demoBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    padding: 12,
    backgroundColor: '#ECFDF5',
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    marginBottom: IOS_STYLES.SPACING.MD,
    borderWidth: 1,
    borderColor: '#A7F3D0',
  },
  demoText: { flex: 1, fontSize: 13, color: COLORS.TEXT_PRIMARY, lineHeight: 20 },
});

export default PaymentHubScreen;
