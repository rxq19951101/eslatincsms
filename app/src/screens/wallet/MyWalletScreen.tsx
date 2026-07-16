/**
 * 我的钱包页面（只读余额与流水；支付轨关闭时无充值入口）
 */

import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StatusBar, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { COLORS, IOS_STYLES, PAYMENT_RAILS_ENABLED } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchWalletBalance, fetchWalletTransactions } from '../../store/slices/walletSlice';
import type { WalletTransaction } from '../../types';
import Icon from '../../components/ui/Icon';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { formatMoneyCOP, formatMoneyCOPShort } from '../../utils/formatMoney';
import { useI18n } from '../../i18n';

const COP_TOP_UP_AMOUNTS = [10000, 20000, 50000];

const MyWalletScreen = () => {
  const { t } = useI18n();

  const dispatch = useAppDispatch();
  const navigation = useNavigation<any>();
  const { balance, transactions, loadingBalance, loadingTx, toppingUp, error } = useAppSelector(
    (s) => s.wallet
  );

  useEffect(() => {
    dispatch(fetchWalletBalance());
    dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
  }, [dispatch]);

  const handleMercadoPagoTopUp = (amount: number) => {
    navigation.navigate('MercadoPagoPayment', {
      amount,
      type: 'top_up',
    });
  };

  const amountText = (amount: number) => {
    const sign = amount >= 0 ? '+' : '-';
    return `${sign}${formatMoneyCOP(Math.abs(amount))}`;
  };

  const renderTx = ({ item, index }: { item: WalletTransaction; index: number }) => {
    const isTopUp = item.type === 'top_up';
    const color = isTopUp ? COLORS.SUCCESS : COLORS.ERROR;
    return (
      <Card
        key={item.id}
        style={[styles.txRow, { marginBottom: index < transactions.length - 1 ? IOS_STYLES.SPACING.SM : 0 }]}
      >
        <View style={styles.txLeft}>
          <View style={styles.txIconContainer}>
            <Icon
              name={isTopUp ? 'add-circle' : 'remove-circle'}
              library="Ionicons"
              size={20}
              color={color}
            />
            <Text style={styles.txTitle}>
              {item.description || (isTopUp ? t.wallet.topUpLabel : t.wallet.chargeLabel)}
            </Text>
          </View>
          <Text style={styles.txTime}>{item.created_at}</Text>
        </View>
        <Text style={[styles.txAmount, { color }]}>{amountText(item.amount)}</Text>
      </Card>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />

      <View style={styles.header}>
        <Text style={styles.headerTitle}>{t.wallet.title}</Text>
      </View>

      <Card style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>{t.wallet.available}</Text>
        <Text style={styles.balanceAmount}>
          {loadingBalance && !balance ? '—' : formatMoneyCOPShort(balance?.balance ?? 0)}
        </Text>

        {PAYMENT_RAILS_ENABLED ? (
          <>
            <View style={styles.topUpRow}>
              {COP_TOP_UP_AMOUNTS.map((amt) => (
                <Button
                  key={amt}
                  title={t.wallet.topUp.replace('{amount}', formatMoneyCOPShort(amt))}
                  onPress={() => handleMercadoPagoTopUp(amt)}
                  variant="secondary"
                  size="small"
                  disabled={toppingUp}
                  style={{ marginRight: IOS_STYLES.SPACING.SM }}
                />
              ))}
            </View>
            <Text style={styles.paymentNote}>{t.wallet.cardNote}</Text>
          </>
        ) : (
          <Text style={styles.paymentNote}>{t.wallet.railsOff}</Text>
        )}
      </Card>

      <View style={styles.transactionsSection}>
        <View style={styles.txHeader}>
          <Text style={styles.sectionTitle}>{t.wallet.transactions}</Text>
          {(loadingTx || toppingUp) && <LoadingSpinner size="small" color={COLORS.IOS_BLUE} />}
        </View>

        {!!error && <Text style={styles.errorText}>{error}</Text>}

        {transactions.length === 0 && !loadingTx ? (
          <View style={styles.emptyState}>
            <Icon name="wallet" library="Ionicons" size={60} color={COLORS.TEXT_SECONDARY} />
            <Text style={styles.emptyText}>{t.wallet.emptyTx}</Text>
          </View>
        ) : (
          <FlatList
            data={transactions}
            keyExtractor={(item) => item.id}
            renderItem={({ item, index }) => renderTx({ item, index })}
            contentContainerStyle={{ paddingBottom: 20 }}
          />
        )}
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
  },
  balanceCard: {
    backgroundColor: COLORS.PRIMARY,
    marginHorizontal: IOS_STYLES.SPACING.MD,
    marginBottom: IOS_STYLES.SPACING.LG,
    padding: IOS_STYLES.SPACING.LG,
    borderRadius: IOS_STYLES.RADIUS.LARGE,
  },
  balanceLabel: {
    fontSize: 14,
    color: '#FFFFFF',
    opacity: 0.8,
    marginBottom: 8,
  },
  balanceAmount: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  topUpRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: IOS_STYLES.SPACING.SM,
  },
  paymentNote: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: '#FFFFFF',
    opacity: 0.85,
    marginTop: IOS_STYLES.SPACING.SM,
    textAlign: 'center',
    lineHeight: 18,
  },
  transactionsSection: {
    flex: 1,
    paddingHorizontal: 20,
  },
  txHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.TEXT_PRIMARY,
  },
  txRow: {
    padding: IOS_STYLES.SPACING.MD,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  txLeft: { flex: 1, paddingRight: IOS_STYLES.SPACING.MD },
  txIconContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.SM,
  },
  txTitle: { fontWeight: IOS_STYLES.FONT_WEIGHT.HEAVY, color: COLORS.TEXT_PRIMARY },
  txTime: {
    marginTop: IOS_STYLES.SPACING.SM,
    color: COLORS.TEXT_SECONDARY,
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
  },
  txAmount: { fontWeight: IOS_STYLES.FONT_WEIGHT.HEAVY },
  errorText: {
    color: COLORS.ERROR,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    marginBottom: IOS_STYLES.SPACING.MD,
  },
  emptyState: {
    padding: IOS_STYLES.SPACING.XL,
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.MD,
  },
  emptyText: {
    color: COLORS.TEXT_SECONDARY,
  },
});

export default MyWalletScreen;
