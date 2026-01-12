/**
 * 我的钱包页面
 */

import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StatusBar, TouchableOpacity, FlatList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS } from '../../constants/config';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { fetchWalletBalance, fetchWalletTransactions, topUp } from '../../store/slices/walletSlice';
import type { WalletTransaction } from '../../types';

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

  const renderTx = ({ item }: { item: WalletTransaction }) => {
    const isTopUp = item.type === 'top_up';
    const color = isTopUp ? COLORS.SUCCESS : COLORS.ERROR;
    return (
      <View style={styles.txRow}>
        <View style={styles.txLeft}>
          <Text style={styles.txTitle}>{item.description || (isTopUp ? '充值' : '充电扣费')}</Text>
          <Text style={styles.txTime}>{item.created_at}</Text>
        </View>
        <Text style={[styles.txAmount, { color }]}>{amountText(item.amount)}</Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      <View style={styles.header}>
        <Text style={styles.headerTitle}>我的钱包</Text>
      </View>

      {/* Balance Card */}
      <View style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>可用余额</Text>
        <Text style={styles.balanceAmount}>
          {loadingBalance && !balance ? '—' : `$${(balance?.balance ?? 0).toFixed(2)}`}
        </Text>
        
        <View style={styles.topUpRow}>
          {[10, 20, 50].map((amt) => (
            <TouchableOpacity
              key={amt}
              style={[styles.topUpButton, toppingUp && styles.disabled]}
              disabled={toppingUp}
              onPress={async () => {
                try {
                  await dispatch(topUp(amt)).unwrap();
                  dispatch(fetchWalletTransactions({ limit: 50, offset: 0 }));
                } catch {
                  // 错误已进入 slice.error
                }
              }}
            >
              <Text style={styles.topUpButtonText}>充值 ${amt}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Transactions */}
      <View style={styles.transactionsSection}>
        <View style={styles.txHeader}>
          <Text style={styles.sectionTitle}>交易记录</Text>
          {(loadingTx || toppingUp) && <ActivityIndicator size="small" color={COLORS.PRIMARY} />}
        </View>

        {!!error && <Text style={styles.errorText}>{error}</Text>}

        {transactions.length === 0 && !loadingTx ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyIcon}>💰</Text>
            <Text style={styles.emptyText}>暂无交易记录</Text>
          </View>
        ) : (
          <FlatList
            data={transactions}
            keyExtractor={(item) => item.id}
            renderItem={renderTx}
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
    marginHorizontal: 20,
    marginBottom: 24,
    padding: 24,
    borderRadius: 16,
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
  topUpButton: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
    marginRight: 10,
    marginTop: 6,
  },
  topUpButtonText: {
    color: COLORS.PRIMARY,
    fontSize: 14,
    fontWeight: '600',
  },
  topUpRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 6,
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
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyIcon: {
    fontSize: 60,
    marginBottom: 12,
  },
  emptyText: {
    fontSize: 14,
    color: COLORS.TEXT_SECONDARY,
  },
  txRow: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  txLeft: { flex: 1, paddingRight: 10 },
  txTitle: { fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  txTime: { marginTop: 6, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  txAmount: { fontWeight: '900' },
  errorText: { color: COLORS.ERROR, fontWeight: '700', marginBottom: 10 },
  disabled: { opacity: 0.6 },
});

export default MyWalletScreen;
