/**
 * 我的钱包页面
 */

import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StatusBar, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchWalletBalance, fetchWalletTransactions, topUp } from '../../store/slices/walletSlice';
import type { WalletTransaction } from '../../types';
import Icon from '../../components/ui/Icon';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';

const MyWalletScreen = () => {
  const dispatch = useAppDispatch();
  const { balance, transactions, loadingBalance, loadingTx, toppingUp, error } = useAppSelector((s) => s.wallet);

  useEffect(() => {
    dispatch(fetchWalletBalance());
    dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
  }, [dispatch]);

  const amountText = (amount: number) => {
    const sign = amount >= 0 ? '+' : '-';
    return `${sign}$${Math.abs(amount).toFixed(2)}`;
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
            <Text style={styles.txTitle}>{item.description || (isTopUp ? '充值' : '充电扣费')}</Text>
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
        <Text style={styles.headerTitle}>我的钱包</Text>
      </View>

      {/* Balance Card */}
      <Card style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>可用余额</Text>
        <Text style={styles.balanceAmount}>
          {loadingBalance && !balance ? '—' : `$${(balance?.balance ?? 0).toFixed(2)}`}
        </Text>
        
        <View style={styles.topUpRow}>
          {[10, 20, 50].map((amt) => (
            <Button
              key={amt}
              title={`充值 $${amt}`}
              onPress={async () => {
                try {
                  await dispatch(topUp(amt)).unwrap();
                  dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
                } catch {
                  // 错误已进入 slice.error
                }
              }}
              variant="secondary"
              size="small"
              disabled={toppingUp}
              style={{ marginRight: IOS_STYLES.SPACING.SM }}
            />
          ))}
        </View>
      </Card>

      {/* Transactions */}
      <View style={styles.transactionsSection}>
        <View style={styles.txHeader}>
          <Text style={styles.sectionTitle}>交易记录</Text>
          {(loadingTx || toppingUp) && (
            <LoadingSpinner size="small" color={COLORS.IOS_BLUE} />
          )}
        </View>

        {!!error && <Text style={styles.errorText}>{error}</Text>}

        {transactions.length === 0 && !loadingTx ? (
          <View style={styles.emptyState}>
            <Icon name="wallet" library="Ionicons" size={60} color={COLORS.TEXT_SECONDARY} />
            <Text style={styles.emptyText}>暂无交易记录</Text>
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
  txTime: { marginTop: IOS_STYLES.SPACING.SM, color: COLORS.TEXT_SECONDARY, fontSize: IOS_STYLES.FONT_SIZE.SMALL },
  txAmount: { fontWeight: IOS_STYLES.FONT_WEIGHT.HEAVY },
  errorText: { color: COLORS.ERROR, fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD, marginBottom: IOS_STYLES.SPACING.MD },
  emptyState: {
    padding: IOS_STYLES.SPACING.XL,
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.MD,
  },
});

export default MyWalletScreen;
