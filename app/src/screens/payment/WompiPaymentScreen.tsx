/**
 * Wompi 支付页面
 * 使用 WebView 加载 Wompi checkout URL
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  ActivityIndicator,
  Alert,
  Linking,
  AppState,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS, IOS_STYLES } from '../../constants/config';
import { getPaymentOrderStatus } from '../../api/payments';
import Button from '../../components/ui/Button';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { useI18n } from '../../i18n';

type WompiPaymentRouteProp = RouteProp<RootStackParamList, 'WompiPayment'>;
type WompiPaymentNavProp = StackNavigationProp<RootStackParamList, 'WompiPayment'>;

const WompiPaymentScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<WompiPaymentNavProp>();
  const route = useRoute<WompiPaymentRouteProp>();
  const { orderId, checkoutUrl } = route.params || {};
  
  const [statusCheckInterval, setStatusCheckInterval] = useState<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // 打开支付页面（外部浏览器）
    if (checkoutUrl) {
      Linking.openURL(checkoutUrl).catch((err) => {
        console.error('Failed to open payment URL:', err);
        Alert.alert(t.common.error, t.payment.openFailed);
      });
    }

    // 如果有 orderId，轮询支付状态
    if (orderId) {
      const interval = setInterval(async () => {
        try {
          const status = await getPaymentOrderStatus(orderId);
          if (status.status === 'approved' || status.status === 'declined' || status.status === 'error' || status.status === 'expired') {
            clearInterval(interval);
            setStatusCheckInterval(null);
            navigation.replace('PaymentResult', {
              orderId,
              status: status.status,
            });
          }
        } catch (error) {
          console.error('Failed to check payment status:', error);
        }
      }, 3000); // 每3秒检查一次
      
      setStatusCheckInterval(interval);
      
      // 监听应用回到前台（用户可能在外部浏览器完成支付后返回）
      const subscription = AppState.addEventListener('change', (nextAppState) => {
        if (nextAppState === 'active') {
          // 应用回到前台，立即检查支付状态
          getPaymentOrderStatus(orderId).then((status) => {
            if (status.status === 'approved' || status.status === 'declined' || status.status === 'error' || status.status === 'expired') {
              if (interval) clearInterval(interval);
              setStatusCheckInterval(null);
              navigation.replace('PaymentResult', {
                orderId,
                status: status.status,
              });
            }
          }).catch((error) => {
            console.error('Failed to check payment status:', error);
          });
        }
      });
      
      return () => {
        clearInterval(interval);
        subscription.remove();
      };
    }
  }, [orderId, checkoutUrl, navigation]);

  const handleClose = () => {
    if (statusCheckInterval) {
      clearInterval(statusCheckInterval);
      setStatusCheckInterval(null);
    }
    navigation.goBack();
  };

  if (!checkoutUrl && !orderId) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <StatusBar barStyle="dark-content" />
        <ScreenHeader
          title={t.payment.title}
          left={<Button title={t.common.close} variant="text" size="small" onPress={handleClose} />}
        />
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{t.payment.invalidLink}</Text>
          <Button title={t.common.back} variant="primary" onPress={handleClose} style={{ marginTop: 20 }} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" />
      
      <ScreenHeader
        title={t.payment.title}
        left={<Button title={t.common.close} variant="text" size="small" onPress={handleClose} />}
      />

      <View style={styles.content}>
        <Text style={styles.title}>{t.payment.opening}</Text>
        <Text style={styles.message}>{t.payment.openBrowser}</Text>
        {orderId && (
          <View style={styles.orderInfo}>
            <Text style={styles.orderLabel}>{t.payment.orderId}</Text>
            <Text style={styles.orderId}>{orderId}</Text>
          </View>
        )}
        <View style={styles.statusContainer}>
          <ActivityIndicator size="small" color={COLORS.IOS_BLUE} />
          <Text style={styles.statusText}>{t.payment.waitingResult}</Text>
        </View>
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
  title: {
    fontSize: IOS_STYLES.FONT_SIZE.TITLE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    color: COLORS.TEXT_PRIMARY,
    marginTop: IOS_STYLES.SPACING.LG,
    marginBottom: IOS_STYLES.SPACING.SM,
    textAlign: 'center',
  },
  message: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
    textAlign: 'center',
    marginBottom: IOS_STYLES.SPACING.XL,
    lineHeight: 24,
  },
  orderInfo: {
    marginTop: IOS_STYLES.SPACING.LG,
    padding: IOS_STYLES.SPACING.MD,
    backgroundColor: COLORS.CARD_BG,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    alignItems: 'center',
    marginBottom: IOS_STYLES.SPACING.LG,
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
  statusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: IOS_STYLES.SPACING.SM,
  },
  statusText: {
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: IOS_STYLES.SPACING.XL,
    gap: IOS_STYLES.SPACING.MD,
  },
  errorText: {
    fontSize: IOS_STYLES.FONT_SIZE.LARGE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    color: COLORS.TEXT_PRIMARY,
    textAlign: 'center',
  },
});

export default WompiPaymentScreen;
