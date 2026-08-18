/**
 * 扫码启动充电（仅支持扫码充电）
 * - Native：使用 expo-camera 扫码
 * - Web：提供手动输入二维码内容（开发调试用）
 */

import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import { CameraView, useCameraPermissions } from 'expo-camera';

import { COLORS } from '../../constants/config';
import type { RootStackParamList } from '../../types';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import RootTabHeader from '../../components/ui/RootTabHeader';
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import { radius, spacing } from '../../theme';
import { parseQrPayload } from '../../utils/qrPayload';

type Nav = StackNavigationProp<RootStackParamList>;

const ScanScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const [manual, setManual] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [scanned, setScanned] = useState(false);

  const [permission, requestPermission] = useCameraPermissions();
  const hasPermission = permission?.granted === true;

  const canUseCamera = Platform.OS !== 'web';

  const hint = useMemo(() => t.scan.manualHint, [t.scan.manualHint]);

  const goToProcess = (payload: string) => {
    const value = payload.trim();
    // The backend/admin exposes the raw token for debugging, while a printed
    // public QR payload uses the `qr:` prefix. Keep the manual Web test path
    // convenient without changing the native scanner contract.
    const normalizedPayload =
      Platform.OS === 'web' && value && !value.startsWith('{') && !value.toLowerCase().startsWith('qr:')
        ? `qr:${value}`
        : value;
    const parsed = parseQrPayload(normalizedPayload);
    if (!parsed) {
      setValidationError(t.scan.invalidQrDetail);
      if (Platform.OS !== 'web') {
        Alert.alert(t.scan.invalidQr, t.scan.invalidQrDetail);
      }
      return;
    }
    setValidationError(null);
    navigation.navigate('ChargingProcess', {
      qrToken: parsed.qrToken,
    });
  };

  return (
    <Screen testID="app-scan-screen" accessibilityLabel={t.scan.title}>
      <RootTabHeader title={t.scan.title} subtitle={t.scan.subtitle} testID="app-scan-header" />
      <View style={styles.container}>

        {(!canUseCamera || !hasPermission) && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t.scan.manualTitle}</Text>
            <Text style={styles.cardHint}>{hint}</Text>
            <TextField
              testID="app-qr-manual-input"
              accessibilityLabel={t.scan.manualTitle}
              value={manual}
              onChangeText={(value) => {
                setManual(value);
                if (validationError) setValidationError(null);
              }}
              placeholder={t.scan.placeholder}
              autoCapitalize="none"
              error={validationError ?? undefined}
            />
            <View style={styles.row}>
              {canUseCamera && !hasPermission && (
                <Button testID="app-camera-permission" title={t.scan.requestCamera} variant="secondary" onPress={requestPermission} style={styles.action} />
              )}
              <Button testID="app-qr-check-submit" title={t.scan.start} onPress={() => goToProcess(manual)} style={styles.action} />
            </View>
          </View>
        )}

        {/* Native camera */}
        {canUseCamera && hasPermission && (
          <View style={styles.cameraWrap}>
            <CameraView
              testID="app-qr-camera"
              accessibilityLabel={t.scan.subtitle}
              style={styles.camera}
              onBarcodeScanned={(result) => {
                if (scanned) return;
                setScanned(true);
                goToProcess(result.data);
                // 给用户一个可重复扫码的入口
                setTimeout(() => setScanned(false), 1200);
              }}
              barcodeScannerSettings={{
                barcodeTypes: ['qr'],
              }}
            />
            <View style={styles.overlay}>
              <View style={styles.scanBox} />
              <Text style={styles.overlayText}>{t.scan.subtitle}</Text>
            </View>
          </View>
        )}
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: spacing.md, paddingBottom: spacing.md },

  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: radius.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  cardTitle: { fontSize: 16, fontWeight: '600', color: COLORS.TEXT_PRIMARY, marginBottom: 8 },
  cardHint: { color: COLORS.TEXT_SECONDARY, lineHeight: 18, marginBottom: 12 },
  row: { flexDirection: 'row', marginTop: 12, gap: 10 },
  action: { flex: 1 },

  cameraWrap: {
    flex: 1,
    borderRadius: radius.lg,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  camera: { flex: 1 },
  overlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scanBox: {
    width: 240,
    height: 240,
    borderRadius: 16,
    borderWidth: 3,
    borderColor: '#FFFFFF',
    backgroundColor: 'transparent',
  },
  overlayText: {
    marginTop: 14,
    color: '#FFFFFF',
    fontWeight: '600',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 6,
  },
});

export default ScanScreen;
