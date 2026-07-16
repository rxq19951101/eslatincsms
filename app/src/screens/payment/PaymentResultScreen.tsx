/**
 * 支付结果页面
 * 显示支付成功/失败/超时状态
 */

import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StatusBar } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { getPaymentOrderStatus } from '../../api/payments';
import { useAppDispatch } from '../../hooks/useRedux';
import { fetchWalletBalance } from '../../store/slices/walletSlice';
import Button from '../../components/ui/Button';
import Icon from '../../components/ui/Icon';
import { useI18n } from '../../i18n';

type PaymentResultRouteProp = RouteProp<RootStackParamList, 'PaymentResult'>;

const PaymentResultScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation();
  const route = useRoute<PaymentResultRouteProp>();
  const { orderId, status } = route.params || {};
  const dispatch = useAppDispatch();

  useEffect(() => {
    // 支付成功后刷新钱包余额
    if (status === 'approved') {
      dispatch(fetchWalletBalance());
    }
  }, [status, dispatch]);

  const getStatusConfig = () => {
    switch (status) {
      case 'approved':
        return {
          icon: 'checkmark-circle' as const,
          iconColor: COLORS.SUCCESS,
          title: t.payment.resultOkTitle,
          message: t.payment.resultOkBody,
        };
      case 'declined':
        return {
          icon: 'close-circle' as const,
          iconColor: COLORS.ERROR,
          title: t.payment.resultDeniedTitle,
          message: t.payment.resultDeniedBody,
        };
      case 'error':
        return {
          icon: 'alert-circle' as const,
          iconColor: COLORS.ERROR,
          title: t.payment.resultErrorTitle,
          message: t.payment.resultErrorBody,
        };
      case 'expired':
        return {
          icon: 'time-outline' as const,
          iconColor: COLORS.WARNING,
          title: t.payment.resultExpiredTitle,
          message: t.payment.resultExpiredBody,
        };
      default:
        return {
          icon: 'help-circle' as const,
          iconColor: COLORS.TEXT_SECONDARY,
          title: t.payment.resultUnknownTitle,
          message: t.payment.resultUnknownBody,
        };
    }
  };

  const config = getStatusConfig();

  const handleDone = () => {
    if (status === 'approved') {
      // 支付成功，返回钱包页面
      navigation.navigate('MainTabs', { screen: 'MyWallet' });
    } else {
      // 支付失败，返回上一页
      navigation.goBack();
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      <View style={styles.content}>
        <Icon name={config.icon} library="Ionicons" size={80} color={config.iconColor} />
        <Text style={styles.title}>{config.title}</Text>
        <Text style={styles.message}>{config.message}</Text>
        
        {orderId && (
          <View style={styles.orderInfo}>
            <Text style={styles.orderLabel}>{t.payment.orderId}</Text>
            <Text style={styles.orderId}>{orderId}</Text>
          </View>
        )}
        <Text style={styles.copNote}>{t.payment.copNote}</Text>
      </View>

      <View style={styles.footer}>
        <Button
          title={status === 'approved' ? t.payment.done : t.common.back}
          variant="primary"
          onPress={handleDone}
          style={styles.button}
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.BACKGROUND,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: IOS_STYLES.SPACING.XL,
  },
  copNote: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
    marginTop: IOS_STYLES.SPACING.LG,
    textAlign: 'center',
  },
  title: {
    fontSize: IOS_STYLES.FONT_SIZE.TITLE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    color: COLORS.TEXT_PRIMARY,
    marginTop: IOS_STYLES.SPACING.LG,
    marginBottom: IOS_STYLES.SPACING.SM,
  },
  message: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: IOS_STYLES.SPACING.XL,
  },
  orderInfo: {
    marginTop: IOS_STYLES.SPACING.LG,
    padding: IOS_STYLES.SPACING.MD,
    backgroundColor: COLORS.CARD_BG,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    alignItems: 'center',
  },
  orderLabel: {
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: IOS_STYLES.SPACING.XS,
  },
  orderId: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    color: COLORS.TEXT_PRIMARY,
  },
  footer: {
    padding: IOS_STYLES.SPACING.MD,
    borderTopWidth: 1,
    borderTopColor: COLORS.BORDER,
  },
  button: {
    width: '100%',
  },
});

export default PaymentResultScreen;
