/**
 * Mercado Pago 支付页面
 * 收集卡信息并创建支付
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList, CardData } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { formatMoneyCOP } from '../../utils/formatMoney';
import { createMercadoPagoPayment, getPaymentOrderStatus } from '../../api/payments';
import { handleApiError } from '../../api/client';
import Button from '../../components/ui/Button';
import ScreenHeader from '../../components/ui/ScreenHeader';
import TextField from '../../components/ui/TextField';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { useI18n, getT } from '../../i18n';

type MercadoPagoPaymentRouteProp = RouteProp<RootStackParamList, 'MercadoPagoPayment'>;
type MercadoPagoNav = StackNavigationProp<RootStackParamList, 'MercadoPagoPayment'>;

/** MP 返回英文错误时转成可操作的说明 */
function formatMercadoPagoPaymentError(apiMessage: string): string {
  if (/Unauthorized use of live credentials/i.test(apiMessage)) {
    return getT().payment.mpCredMismatch;
  }
  return apiMessage;
}

const MercadoPagoPaymentScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<MercadoPagoNav>();
  const route = useRoute<MercadoPagoPaymentRouteProp>();
  const { amount, type, metadata } = route.params || {};
  
  const user = useSelector((state: RootState) => state.auth.user);
  const [loading, setLoading] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (pollStopTimeoutRef.current) {
        clearTimeout(pollStopTimeoutRef.current);
        pollStopTimeoutRef.current = null;
      }
    };
  }, []);
  
  // 表单状态
  const [cardNumber, setCardNumber] = useState('');
  const [expMonth, setExpMonth] = useState('');
  const [expYear, setExpYear] = useState('');
  const [cvc, setCvc] = useState('');
  const [holderName, setHolderName] = useState('');
  const [email, setEmail] = useState(user?.email || '');
  
  // 验证状态
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  // 测试卡快捷填充（仅开发/测试环境）
  const fillTestCard = (scenario: 'approved' | 'pending' | 'rejected') => {
    const testCards = {
      approved: {
        number: '4060 4914 4768 0666',
        expMonth: '11',
        expYear: '25',
        cvc: '123',
        holderName: 'APRO',
        email: user?.email || 'test@example.com',
      },
      pending: {
        number: '4060 4914 4768 0666',
        expMonth: '11',
        expYear: '25',
        cvc: '123',
        holderName: 'CONT',
        email: user?.email || 'test@example.com',
      },
      rejected: {
        number: '4060 4914 4768 0666',
        expMonth: '11',
        expYear: '25',
        cvc: '123',
        holderName: 'CALL',
        email: user?.email || 'test@example.com',
      },
    };
    
    const card = testCards[scenario];
    setCardNumber(card.number);
    setExpMonth(card.expMonth);
    setExpYear(card.expYear);
    setCvc(card.cvc);
    setHolderName(card.holderName);
    setEmail(card.email);
    setErrors({});
  };
  
  // 验证邮箱格式
  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };
  
  // 验证表单
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    // 验证卡号（移除空格后验证）
    const cleanCardNumber = cardNumber.replace(/\s/g, '');
    if (!cleanCardNumber || cleanCardNumber.length < 13 || cleanCardNumber.length > 19) {
      newErrors.cardNumber = t.payment.invalidCard;
    }
    
    // 验证过期月份
    const month = parseInt(expMonth, 10);
    if (!expMonth || month < 1 || month > 12) {
      newErrors.expMonth = t.payment.invalidMonth;
    }
    
    // 验证过期年份
    const year = parseInt(expYear, 10);
    const currentYear = new Date().getFullYear() % 100;
    if (!expYear || year < currentYear || year > 99) {
      newErrors.expYear = t.payment.invalidYear;
    }
    
    // 验证 CVV
    if (!cvc || cvc.length < 3 || cvc.length > 4) {
      newErrors.cvc = t.payment.invalidCvc;
    }
    
    // 验证持卡人姓名
    if (!holderName || holderName.trim().length < 2) {
      newErrors.holderName = t.payment.invalidHolder;
    }
    
    // 验证邮箱（MP 强制要求）
    if (!email || !validateEmail(email)) {
      newErrors.email = t.payment.invalidEmail;
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };
  
  // 格式化卡号（添加空格）
  const formatCardNumber = (text: string): string => {
    const cleaned = text.replace(/\s/g, '');
    const formatted = cleaned.match(/.{1,4}/g)?.join(' ') || cleaned;
    return formatted;
  };
  
  // 处理支付
  const handlePayment = async () => {
    if (!validateForm()) {
      Alert.alert(t.common.error, t.payment.formInvalid);
      return;
    }
    
    if (!amount || !type) {
      Alert.alert(t.common.error, t.payment.missingPayInfo);
      return;
    }
    
    setLoading(true);
    
    try {
      const cardData: CardData = {
        number: cardNumber.replace(/\s/g, ''),
        expMonth: expMonth.padStart(2, '0'),
        expYear: `20${expYear}`,
        cvc,
        holderName: holderName.trim(),
      };
      
      const result = await createMercadoPagoPayment(
        amount,
        cardData,
        email.trim(),
        type,
        metadata
      );
      
      // 支付创建成功，轮询状态（必须在终态时停止定时器，否则 replace 后仍会每 3s 再次打开结果页）
      if (result.order_id) {
        const stopPolling = () => {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          if (pollStopTimeoutRef.current) {
            clearTimeout(pollStopTimeoutRef.current);
            pollStopTimeoutRef.current = null;
          }
        };

        const checkStatus = async (): Promise<boolean> => {
          try {
            const status = await getPaymentOrderStatus(result.order_id);
            if (status.status === 'approved' || status.status === 'declined' || 
                status.status === 'error' || status.status === 'expired') {
              stopPolling();
              navigation.replace('PaymentResult', {
                orderId: result.order_id,
                status: status.status,
              });
              return true;
            }
          } catch (error) {
            console.error('Failed to check payment status:', error);
          }
          return false;
        };
        
        const doneOnFirst = await checkStatus();
        if (doneOnFirst) {
          return;
        }

        pollIntervalRef.current = setInterval(() => {
          void checkStatus();
        }, 3000);

        pollStopTimeoutRef.current = setTimeout(() => {
          stopPolling();
        }, 30000);
      }
    } catch (error: unknown) {
      console.error('Payment error:', error);
      const { message } = handleApiError(error);
      const detail = message?.trim() ? formatMercadoPagoPaymentError(message) : '';
      Alert.alert(t.payment.payFailed, detail || t.payment.payFailedBody);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScreenHeader
          title={t.payment.title}
          left={<Button title={t.common.close} variant="text" size="small" onPress={() => navigation.goBack()} />}
        />
        
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.amountContainer}>
            <Text style={styles.amountLabel}>{t.payment.amountLabel}</Text>
            <Text style={styles.amountValue}>{formatMoneyCOP(amount ?? 0)}</Text>
          </View>
          
          <View style={styles.form}>
            <View style={styles.sectionHeader}>
              {[
                <Text key="sectionTitle" style={styles.sectionTitle}>
                  {t.payment.cardInfo}
                </Text>,
                __DEV__ ? (
                  <View key="testCards" style={styles.testCardButtons}>
                    {[
                      <Button
                        key="approved"
                        title={t.payment.testApprove}
                        variant="text"
                        onPress={() => fillTestCard('approved')}
                        style={styles.testCardButton}
                      />,
                      <Button
                        key="pending"
                        title={t.payment.testPending}
                        variant="text"
                        onPress={() => fillTestCard('pending')}
                        style={styles.testCardButton}
                      />,
                      <Button
                        key="rejected"
                        title={t.payment.testReject}
                        variant="text"
                        onPress={() => fillTestCard('rejected')}
                        style={styles.testCardButton}
                      />,
                    ]}
                  </View>
                ) : null,
              ]}
            </View>
            
            {/* 卡号 */}
            <View style={styles.inputGroup}>
              <TextField
                label={t.payment.cardNumber}
                inputStyle={styles.input}
                error={errors.cardNumber || undefined}
                placeholder={t.payment.cardNumber}
                value={cardNumber}
                onChangeText={(text) => {
                  const formatted = formatCardNumber(text.replace(/\D/g, ''));
                  setCardNumber(formatted);
                  if (errors.cardNumber) {
                    setErrors({ ...errors, cardNumber: '' });
                  }
                }}
                keyboardType="numeric"
                maxLength={19}
                autoComplete="cc-number"
              />
            </View>
            
            {/* 过期日期和 CVV — 行内子 View 之间不能有裸空白，否则 RN Web 会把缩进当成非法文本节点 */}
            <View style={styles.row}>
              {[
                <View key="expMonth" style={[styles.inputGroup, styles.flex1]}>
                  <TextField
                    label={t.payment.expMonth}
                    inputStyle={styles.input}
                    error={errors.expMonth || undefined}
                    placeholder={t.payment.expMonth}
                    value={expMonth}
                    onChangeText={(text) => {
                      const cleaned = text.replace(/\D/g, '').slice(0, 2);
                      setExpMonth(cleaned);
                      if (errors.expMonth) {
                        setErrors({ ...errors, expMonth: '' });
                      }
                    }}
                    keyboardType="numeric"
                    maxLength={2}
                  />
                </View>,
                <View key="expYear" style={[styles.inputGroup, styles.flex1, styles.marginLeft]}>
                  <TextField
                    label={t.payment.expYear}
                    inputStyle={styles.input}
                    error={errors.expYear || undefined}
                    placeholder={t.payment.expYear}
                    value={expYear}
                    onChangeText={(text) => {
                      const cleaned = text.replace(/\D/g, '').slice(0, 2);
                      setExpYear(cleaned);
                      if (errors.expYear) {
                        setErrors({ ...errors, expYear: '' });
                      }
                    }}
                    keyboardType="numeric"
                    maxLength={2}
                  />
                </View>,
                <View key="cvc" style={[styles.inputGroup, styles.flex1, styles.marginLeft]}>
                  <TextField
                    label={t.payment.cvc}
                    inputStyle={styles.input}
                    error={errors.cvc || undefined}
                    placeholder={t.payment.cvc}
                    value={cvc}
                    onChangeText={(text) => {
                      const cleaned = text.replace(/\D/g, '').slice(0, 4);
                      setCvc(cleaned);
                      if (errors.cvc) {
                        setErrors({ ...errors, cvc: '' });
                      }
                    }}
                    keyboardType="numeric"
                    maxLength={4}
                    secureTextEntry
                  />
                </View>,
              ]}
            </View>
            
            {/* 持卡人姓名 */}
            <View style={styles.inputGroup}>
              <TextField
                label={t.payment.holderName}
                inputStyle={styles.input}
                error={errors.holderName || undefined}
                placeholder={t.payment.holderName}
                value={holderName}
                onChangeText={(text) => {
                  setHolderName(text);
                  if (errors.holderName) {
                    setErrors({ ...errors, holderName: '' });
                  }
                }}
                autoCapitalize="words"
                autoComplete="name"
              />
            </View>
            
            {/* 邮箱 */}
            <View style={styles.inputGroup}>
              <TextField
                label={t.payment.emailRequired}
                inputStyle={styles.input}
                error={errors.email || undefined}
                placeholder={t.auth.emailPlaceholder}
                value={email}
                onChangeText={(text) => {
                  setEmail(text);
                  if (errors.email) {
                    setErrors({ ...errors, email: '' });
                  }
                }}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
              />
            </View>
          </View>
          
          <Button
            title={loading ? t.payment.processing : t.payment.confirmPay}
            variant="primary"
            onPress={handlePayment}
            disabled={loading}
            style={styles.payButton}
          />
          
          {loading && (
            <View style={styles.loadingContainer}>
              {[
                <ActivityIndicator key="loading" size="small" color={COLORS.IOS_BLUE} />,
                <Text key="loadingText" style={styles.loadingText}>
                  {t.payment.processingPay}
                </Text>,
              ]}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  keyboardView: {
    flex: 1,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: IOS_STYLES.SPACING.MD,
  },
  amountContainer: {
    backgroundColor: COLORS.CARD_BG,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    padding: IOS_STYLES.SPACING.LG,
    alignItems: 'center',
    marginBottom: IOS_STYLES.SPACING.LG,
    ...IOS_STYLES.SHADOW.SMALL,
  },
  amountLabel: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: IOS_STYLES.SPACING.XS,
  },
  amountValue: {
    fontSize: IOS_STYLES.FONT_SIZE.HEADLINE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    color: COLORS.TEXT_PRIMARY,
  },
  form: {
    marginBottom: IOS_STYLES.SPACING.LG,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: IOS_STYLES.SPACING.MD,
  },
  sectionTitle: {
    fontSize: IOS_STYLES.FONT_SIZE.LARGE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    color: COLORS.TEXT_PRIMARY,
  },
  testCardButtons: {
    flexDirection: 'row',
    gap: IOS_STYLES.SPACING.XS,
  },
  testCardButton: {
    paddingHorizontal: IOS_STYLES.SPACING.SM,
    paddingVertical: IOS_STYLES.SPACING.XS,
    minWidth: 60,
  },
  inputGroup: {
    marginBottom: IOS_STYLES.SPACING.MD,
  },
  input: {
    backgroundColor: COLORS.CARD_BG,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    borderRadius: IOS_STYLES.RADIUS.SMALL,
    padding: IOS_STYLES.SPACING.MD,
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_PRIMARY,
  },
  row: {
    flexDirection: 'row',
  },
  flex1: {
    flex: 1,
  },
  marginLeft: {
    marginLeft: IOS_STYLES.SPACING.SM,
  },
  payButton: {
    marginTop: IOS_STYLES.SPACING.LG,
  },
  loadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: IOS_STYLES.SPACING.MD,
    gap: IOS_STYLES.SPACING.SM,
  },
  loadingText: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
  },
});

export default MercadoPagoPaymentScreen;
