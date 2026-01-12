/**
 * 添加支付方式（简化版，本地存储）
 */

import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import type { RootStackParamList, PaymentMethod } from '../../types';
import { addPaymentMethod, getPaymentMethods, savePaymentMethods } from '../../utils/paymentMethodsStorage';

type Nav = StackNavigationProp<RootStackParamList, 'AddPayment'>;

const AddPaymentScreen = () => {
  const navigation = useNavigation<Nav>();
  const [type, setType] = useState<PaymentMethod['type']>('visa');
  const [lastFour, setLastFour] = useState('');
  const [saving, setSaving] = useState(false);

  const isLastFourValid = useMemo(() => {
    const s = lastFour.trim();
    if (!s) return true; // 可选
    return /^\d{4}$/.test(s);
  }, [lastFour]);

  const onSave = async () => {
    if (!isLastFourValid) {
      Alert.alert('输入有误', '卡号后四位需要是 4 位数字（也可以不填）');
      return;
    }
    setSaving(true);
    try {
      const existing = await getPaymentMethods();
      const isFirst = existing.length === 0;

      const method: PaymentMethod = {
        id: `pm_${Date.now()}`,
        type,
        last_four: lastFour.trim() || undefined,
        is_default: isFirst,
      };

      // 新增到本地列表
      const next = await addPaymentMethod(method);

      // 若不是第一张，也允许用户“新增即默认”——这里保持：只有第一张自动默认
      // 保证列表中至少一个默认
      if (!next.some((m) => m.is_default) && next.length > 0) {
        next[0] = { ...next[0], is_default: true };
        await savePaymentMethods(next);
      }

      navigation.goBack();
    } catch {
      Alert.alert('保存失败', '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>添加支付方式</Text>
        <View style={styles.headerRight} />
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>类型</Text>
        <View style={styles.typeRow}>
          {([
            ['visa', 'VISA'],
            ['mastercard', 'Mastercard'],
            ['paypal', 'PayPal'],
            ['apple_pay', 'Apple Pay'],
            ['google_pay', 'Google Pay'],
          ] as Array<[PaymentMethod['type'], string]>).map(([v, t]) => (
            <TouchableOpacity
              key={v}
              style={[styles.typeChip, type === v && styles.typeChipActive]}
              onPress={() => setType(v)}
            >
              <Text style={[styles.typeText, type === v && styles.typeTextActive]}>{t}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={[styles.label, { marginTop: 14 }]}>卡号后四位（可选）</Text>
        <TextInput
          value={lastFour}
          onChangeText={setLastFour}
          placeholder="例如 4242"
          keyboardType="numeric"
          maxLength={4}
          style={styles.input}
        />
        {!isLastFourValid && <Text style={styles.error}>请输入 4 位数字</Text>}
      </View>

      <View style={styles.bottomBar}>
        <TouchableOpacity style={[styles.btn, styles.primary, saving && styles.disabled]} disabled={saving} onPress={onSave}>
          <Text style={styles.primaryText}>{saving ? '保存中...' : '保存'}</Text>
        </TouchableOpacity>
      </View>
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
  headerRight: { width: 44 },
  card: {
    margin: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  label: { color: COLORS.TEXT_SECONDARY, fontSize: 12, marginBottom: 6 },
  typeRow: { flexDirection: 'row', flexWrap: 'wrap' },
  typeChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#E5E7EB',
    marginRight: 10,
    marginBottom: 10,
  },
  typeChipActive: { backgroundColor: COLORS.PRIMARY },
  typeText: { fontWeight: '800', color: COLORS.TEXT_PRIMARY, fontSize: 12 },
  typeTextActive: { color: '#FFFFFF' },
  input: {
    height: 44,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    paddingHorizontal: 12,
    backgroundColor: '#FFFFFF',
  },
  error: { marginTop: 8, color: COLORS.ERROR, fontWeight: '700' },
  bottomBar: {
    padding: 12,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  btn: { height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY },
  primaryText: { color: '#FFFFFF', fontWeight: '900' },
  disabled: { opacity: 0.6 },
});

export default AddPaymentScreen;

