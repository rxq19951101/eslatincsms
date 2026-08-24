/** Add a saved card through the server-hosted Mercado Pago checkout. */

import React, { useState } from 'react';
import { Alert, Linking, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList } from '../../types';
import { createSaveCardCheckoutSession, isServerCheckoutUrl } from '../../api/payments';
import { trackCheckoutSession } from '../../features/payment/checkoutCoordinator';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Screen from '../../components/ui/Screen';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';

type Nav = StackNavigationProp<RootStackParamList, 'AddPayment'>;

const AddPaymentScreen = () => {
  const { t } = useI18n();
  const navigation = useNavigation<Nav>();
  const [opening, setOpening] = useState(false);

  const onOpenCheckout = async () => {
    if (opening) return;
    setOpening(true);
    try {
      const session = await createSaveCardCheckoutSession();
      if (!isServerCheckoutUrl(session.checkout_url)) {
        throw new Error('insecure_checkout_url');
      }
      await trackCheckoutSession(session);
      await Linking.openURL(session.checkout_url);
      navigation.goBack();
    } catch {
      Alert.alert(t.common.error, t.payment.openFailed);
    } finally {
      setOpening(false);
    }
  };

  return (
    <Screen>
      <ScreenHeader title={t.payment.addMethod} onBack={() => navigation.goBack()} />

      <Card style={styles.card}>
        <Text style={styles.title}>{t.payment.secureCardTitle}</Text>
        <Text style={styles.body}>{t.payment.secureCardBody}</Text>
        <Text style={styles.note}>{t.payment.secureCardNote}</Text>
      </Card>

      <View style={styles.bottomBar}>
        <Button
          title={opening ? t.payment.opening : t.payment.continueToSecurePage}
          disabled={opening}
          loading={opening}
          onPress={() => void onOpenCheckout()}
          size="large"
        />
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  card: { margin: 16, padding: 18 },
  title: { color: COLORS.TEXT_PRIMARY, fontSize: 18, fontWeight: '900', marginBottom: 10 },
  body: { color: COLORS.TEXT_PRIMARY, fontSize: 15, lineHeight: 23 },
  note: { color: COLORS.TEXT_SECONDARY, fontSize: 13, lineHeight: 20, marginTop: 16 },
  bottomBar: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
});

export default AddPaymentScreen;
