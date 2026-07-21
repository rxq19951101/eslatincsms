/**
 * 充电前支付方式条（Uber 式占位）：展示 COP 钱包余额与扣款说明。
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Icon from '../ui/Icon';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { formatMoneyCOPShort } from '../../utils/formatMoney';
import { useI18n } from '../../i18n';

export interface PaymentMethodBarProps {
  balanceCOP: number | null;
  loading?: boolean;
  onPressTopUp?: () => void;
}

export const PaymentMethodBar: React.FC<PaymentMethodBarProps> = ({
  balanceCOP,
  loading,
  onPressTopUp,
}) => {
  const { t } = useI18n();
  const balText =
    loading && balanceCOP === null ? t.wallet.loadingBalance : formatMoneyCOPShort(balanceCOP ?? 0);

  return (
    <View testID="app-charging-wallet" accessibilityLabel={balText} style={styles.wrap}>
      <View style={styles.row}>
        <Icon name="wallet" library="Ionicons" size={22} color={COLORS.PRIMARY} />
        <View style={styles.mid}>
          <Text style={styles.title}>{t.wallet.paymentMethod}</Text>
          <Text style={styles.sub}>{t.wallet.walletBalance} · {t.wallet.currencyCop}</Text>
        </View>
        <Text style={styles.amount}>{balText}</Text>
      </View>
      <Text style={styles.hint}>
        {onPressTopUp
          ? t.wallet.chargeHint
          : t.wallet.chargeHintRailsOff}
      </Text>
      {typeof onPressTopUp === 'function' && (
        <TouchableOpacity style={styles.linkRow} onPress={onPressTopUp} accessibilityRole="button">
          <Text style={styles.link}>{t.wallet.goTopUp}</Text>
          <Icon name="chevron-forward" library="Ionicons" size={18} color={COLORS.PRIMARY} />
        </TouchableOpacity>
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
