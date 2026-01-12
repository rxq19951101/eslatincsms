/**
 * 支付方式管理（简化版，使用本地存储）
 */

import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList, PaymentMethod } from '../../types';
import { deletePaymentMethod, getPaymentMethods, setDefaultPaymentMethod } from '../../utils/paymentMethodsStorage';

type Nav = StackNavigationProp<RootStackParamList, 'PaymentMethods'>;

const PaymentMethodsScreen = () => {
  const navigation = useNavigation<Nav>();
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setMethods(await getPaymentMethods());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [])
  );

  const onDelete = (id: string) => {
    Alert.alert('删除支付方式', '确定要删除吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => setMethods(await deletePaymentMethod(id)),
      },
    ]);
  };

  const onSetDefault = async (id: string) => {
    setMethods(await setDefaultPaymentMethod(id));
  };

  const renderItem = ({ item }: { item: PaymentMethod }) => {
    const label = item.type.toUpperCase();
    const suffix = item.last_four ? `**** ${item.last_four}` : '';
    return (
      <TouchableOpacity style={styles.card} onPress={() => onSetDefault(item.id)} disabled={loading}>
        <View style={styles.left}>
          <Text style={styles.title}>
            {label} {suffix}
          </Text>
          <Text style={styles.subTitle}>{item.is_default ? '默认支付方式' : '点击设为默认'}</Text>
        </View>
        <View style={styles.right}>
          {item.is_default && <Text style={styles.badge}>默认</Text>}
          <TouchableOpacity style={styles.deleteBtn} onPress={() => onDelete(item.id)}>
            <Text style={styles.deleteText}>删除</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>支付方式</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => navigation.navigate('AddPayment')}>
          <Text style={styles.addText}>添加</Text>
        </TouchableOpacity>
      </View>

      {methods.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyIcon}>💳</Text>
          <Text style={styles.centerText}>{loading ? '加载中...' : '暂无支付方式'}</Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={() => navigation.navigate('AddPayment')}>
            <Text style={styles.primaryText}>添加支付方式</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={methods}
          keyExtractor={(it) => it.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 24 }}
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  header: {
    height: 56,
    backgroundColor: '#FFFFFF',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.BORDER,
  },
  backBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 22, color: COLORS.TEXT_PRIMARY },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  addBtn: { width: 64, height: 44, alignItems: 'flex-end', justifyContent: 'center' },
  addText: { color: COLORS.PRIMARY, fontWeight: '900' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  emptyIcon: { fontSize: 56, marginBottom: 10 },
  centerText: { color: COLORS.TEXT_SECONDARY },
  primaryBtn: { marginTop: 16, backgroundColor: COLORS.PRIMARY, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12 },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    marginBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  left: { flex: 1, paddingRight: 10 },
  title: { fontWeight: '900', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, fontSize: 12 },
  right: { alignItems: 'flex-end' },
  badge: { color: COLORS.SUCCESS, fontWeight: '900', marginBottom: 6 },
  deleteBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: '#FEE2E2' },
  deleteText: { color: COLORS.ERROR, fontWeight: '900', fontSize: 12 },
});

export default PaymentMethodsScreen;

