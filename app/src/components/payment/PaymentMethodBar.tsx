/**
 * 充电前支付方式条（Uber 式占位）：展示 COP 钱包余额与扣款说明。
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Icon from '../ui/Icon';
import Badge from '../ui/Badge';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { formatMoneyCOPShort } from '../../utils/formatMoney';
import { useI18n } from '../../i18n';
import type { CanonicalPaymentMethod } from '../../types';
import { getPaymentMethodTypeLabelKey } from '../../api/payments';

export type ChargingPaymentSelection = 'wallet' | 'direct_card';

export interface PaymentMethodBarProps {
  balanceCOP: number | null;
  loading?: boolean;
  onPressTopUp?: () => void;
  allowDirectCard?: boolean;
  selectedMethod?: ChargingPaymentSelection;
  onMethodChange?: (method: ChargingPaymentSelection) => void;
  savedPaymentMethods?: CanonicalPaymentMethod[];
  selectedSavedPaymentMethodId?: string | null;
  onSavedPaymentMethodChange?: (paymentMethodId: string | null) => void;
  savedPaymentMethodsLoading?: boolean;
  savedPaymentMethodsError?: boolean;
  onRetrySavedPaymentMethods?: () => void;
  cardChoicesDisabled?: boolean;
}

export const PaymentMethodBar: React.FC<PaymentMethodBarProps> = ({
  balanceCOP,
  loading,
  onPressTopUp,
  allowDirectCard = false,
  selectedMethod = 'wallet',
  onMethodChange,
  savedPaymentMethods = [],
  selectedSavedPaymentMethodId = null,
  onSavedPaymentMethodChange,
  savedPaymentMethodsLoading = false,
  savedPaymentMethodsError = false,
  onRetrySavedPaymentMethods,
  cardChoicesDisabled = false,
}) => {
  const { t } = useI18n();
  const balText =
    loading && balanceCOP === null ? t.wallet.loadingBalance : formatMoneyCOPShort(balanceCOP ?? 0);

  return (
    <View testID="app-charging-payment-methods" style={styles.wrap}>
      <Text style={styles.sectionTitle}>{t.charging.paymentMethodTitle}</Text>
      <TouchableOpacity
        testID="app-charging-payment-wallet"
        accessibilityRole="radio"
        accessibilityState={{ selected: selectedMethod === 'wallet' }}
        style={[styles.option, selectedMethod === 'wallet' && styles.selectedOption]}
        onPress={() => onMethodChange?.('wallet')}
      >
        <Icon name="wallet" library="Ionicons" size={22} color={COLORS.PRIMARY} />
        <View style={styles.mid}>
          <Text style={styles.title}>{t.wallet.paymentMethod}</Text>
          <Text style={styles.sub}>{t.wallet.walletBalance} · {t.wallet.currencyCop}</Text>
        </View>
        <Text style={styles.amount}>{balText}</Text>
      </TouchableOpacity>
      {selectedMethod === 'wallet' && (
        <>
          <Text style={styles.hint}>
            {onPressTopUp ? t.wallet.chargeHint : t.wallet.chargeHintRailsOff}
          </Text>
          {typeof onPressTopUp === 'function' && (
            <TouchableOpacity style={styles.linkRow} onPress={onPressTopUp} accessibilityRole="button">
              <Text style={styles.link}>{t.wallet.goTopUp}</Text>
              <Icon name="chevron-forward" library="Ionicons" size={18} color={COLORS.PRIMARY} />
            </TouchableOpacity>
          )}
        </>
      )}

      {allowDirectCard && (
        <>
          <TouchableOpacity
            testID="app-charging-payment-card"
            accessibilityRole="radio"
            accessibilityState={{ selected: selectedMethod === 'direct_card' }}
            style={[styles.option, styles.cardOption, selectedMethod === 'direct_card' && styles.selectedOption]}
            onPress={() => onMethodChange?.('direct_card')}
          >
            <Icon name="card" library="Ionicons" size={22} color={COLORS.PRIMARY} />
            <View style={styles.mid}>
              <Text style={styles.title}>{t.charging.directCardTitle}</Text>
              <Text style={styles.sub}>{t.charging.directCardHint}</Text>
            </View>
          </TouchableOpacity>

          {selectedMethod === 'direct_card' && (
            <View testID="app-charging-card-options" style={styles.cardOptions}>
              <TouchableOpacity
                testID="app-charging-payment-new-card"
                accessibilityRole="radio"
                accessibilityState={{
                  selected: selectedSavedPaymentMethodId === null,
                  disabled: cardChoicesDisabled,
                }}
                accessibilityLabel={`${t.charging.newCard}. ${t.charging.newCardHint}`}
                disabled={cardChoicesDisabled}
                style={[
                  styles.cardChoice,
                  selectedSavedPaymentMethodId === null && styles.selectedCardChoice,
                  cardChoicesDisabled && styles.disabledChoice,
                ]}
                onPress={() => onSavedPaymentMethodChange?.(null)}
              >
                <Text style={styles.cardChoiceText}>{t.charging.newCard}</Text>
                <Text style={styles.cardChoiceHint}>{t.charging.newCardHint}</Text>
              </TouchableOpacity>
              {savedPaymentMethodsLoading && (
                <Text style={styles.cardChoiceHint}>{t.common.loading}</Text>
              )}
              {savedPaymentMethodsError && (
                <View accessibilityRole="alert" style={styles.savedCardsError}>
                  <Text style={styles.cardChoiceHint}>{t.charging.savedCardsLoadFailed}</Text>
                  {onRetrySavedPaymentMethods && (
                    <TouchableOpacity
                      accessibilityRole="button"
                      accessibilityLabel={t.common.retry}
                      onPress={onRetrySavedPaymentMethods}
                      style={styles.retrySavedCards}
                    >
                      <Text style={styles.retrySavedCardsText}>{t.common.retry}</Text>
                    </TouchableOpacity>
                  )}
                </View>
              )}
              {savedPaymentMethods.map((method) => {
                const brand = method.brand?.trim() || t.payment.unknownBrand;
                const typeLabel = t.payment[getPaymentMethodTypeLabelKey(method.payment_type)];
                const label = `${brand} · •••• ${method.last_four || '—'}`;
                const accessibilityLabel = [
                  label,
                  typeLabel,
                  method.is_default ? t.payment.default : null,
                  t.charging.savedCardHint,
                ].filter(Boolean).join('. ');
                return (
                  <TouchableOpacity
                    key={method.id}
                    testID={`app-charging-payment-card-${method.id}`}
                    accessibilityRole="radio"
                    accessibilityLabel={accessibilityLabel}
                    accessibilityState={{
                      selected: selectedSavedPaymentMethodId === method.id,
                      disabled: cardChoicesDisabled,
                    }}
                    disabled={cardChoicesDisabled}
                    style={[
                      styles.cardChoice,
                      selectedSavedPaymentMethodId === method.id && styles.selectedCardChoice,
                      cardChoicesDisabled && styles.disabledChoice,
                    ]}
                    onPress={() => onSavedPaymentMethodChange?.(method.id)}
                  >
                    <View style={styles.savedCardHeader}>
                      <Text style={styles.cardChoiceText}>{label}</Text>
                      {method.is_default && <Badge label={t.payment.default} variant="success" />}
                    </View>
                    <Text style={styles.cardChoiceHint}>{typeLabel} · {t.charging.savedCardHint}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: COLORS.CARD_BG,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    padding: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.MD,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  sectionTitle: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    fontWeight: '700',
    color: COLORS.TEXT_PRIMARY,
    marginBottom: IOS_STYLES.SPACING.SM,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: IOS_STYLES.SPACING.SM,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  cardOption: { marginTop: IOS_STYLES.SPACING.SM },
  selectedOption: { borderColor: COLORS.PRIMARY, backgroundColor: `${COLORS.PRIMARY}12` },
  cardOptions: { marginTop: IOS_STYLES.SPACING.SM, gap: IOS_STYLES.SPACING.XS },
  cardChoice: {
    padding: IOS_STYLES.SPACING.SM,
    borderRadius: IOS_STYLES.RADIUS.SMALL,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  selectedCardChoice: { borderColor: COLORS.PRIMARY },
  disabledChoice: { opacity: 0.55 },
  cardChoiceText: { color: COLORS.TEXT_PRIMARY, fontSize: 14, fontWeight: '600' },
  cardChoiceHint: { color: COLORS.TEXT_SECONDARY, fontSize: 12, marginTop: 2 },
  savedCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: IOS_STYLES.SPACING.SM,
  },
  savedCardsError: { marginTop: IOS_STYLES.SPACING.XS },
  retrySavedCards: { alignSelf: 'flex-start', marginTop: IOS_STYLES.SPACING.XS, minHeight: 36, justifyContent: 'center' },
  retrySavedCardsText: { color: COLORS.PRIMARY, fontWeight: '700' },
  mid: { flex: 1 },
  title: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    fontWeight: '600',
    color: COLORS.TEXT_PRIMARY,
  },
  sub: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
    marginTop: 2,
  },
  amount: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    fontWeight: '700',
    color: COLORS.TEXT_PRIMARY,
  },
  hint: {
    marginTop: IOS_STYLES.SPACING.SM,
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    lineHeight: 18,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: IOS_STYLES.SPACING.SM,
    justifyContent: 'flex-end',
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.PRIMARY,
  },
});
