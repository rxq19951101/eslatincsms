/**
 * 添加支付方式（简化版，本地存储）
 */

import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList, PaymentMethod } from '../../types';
import { addPaymentMethod, getPaymentMethods, savePaymentMethods } from '../../utils/paymentMethodsStorage';
import ScreenHeader from '../../components/ui/ScreenHeader';

type Nav = StackNavigationProp<RootStackParamList, 'AddPayment'>;

const AddPaymentScreen = () => {
  const { t } = useI18n();

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
      Alert.alert(t.payment.lastFourAlertTitle, t.payment.lastFourAlertBody);
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
      Alert.alert(t.common.error, t.payment.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader title={t.payment.addMethodDemo} onBack={() => navigation.goBack()} />

      <View style={styles.demoBanner}>
        <Text style={styles.demoBannerText}>
          {t.payment.addMethodHint}
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>{t.payment.type}</Text>
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

        <Text style={[styles.label, { marginTop: 14 }]}>{t.payment.lastFour}</Text>
        <TextInput
          value={lastFour}
          onChangeText={setLastFour}
          placeholder={t.payment.lastFourPlaceholder}
          keyboardType="numeric"
          maxLength={4}
          style={styles.input}
        />
        {!isLastFourValid && <Text style={styles.error}>{t.payment.lastFourInvalid}</Text>}
      </View>

      <View style={styles.bottomBar}>
        <TouchableOpacity style={[styles.btn, styles.primary, saving && styles.disabled]} disabled={saving} onPress={onSave}>
          <Text style={styles.primaryText}>{saving ? t.payment.saving : t.common.save}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND },
  demoBanner: {
    marginHorizontal: 16,
    marginTop: 8,
    padding: 12,
    backgroundColor: '#FFFBEB',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FDE68A',
  },
  demoBannerText: { fontSize: 13, color: COLORS.TEXT_PRIMARY, lineHeight: 20 },
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

