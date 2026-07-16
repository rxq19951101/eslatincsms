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
import TextField from '../../components/ui/TextField';
import Button from '../../components/ui/Button';
import { radius, spacing, typography } from '../../theme';

type Nav = StackNavigationProp<RootStackParamList>;

type ParsedQr = { qrToken: string };

function parseQrPayload(raw: string): ParsedQr | null {
  const s = (raw || '').trim();
  if (!s) return null;

  // 1) JSON: {"qrToken":"..."} 或 {"qr_token":"..."}
  if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
    try {
      const obj: any = JSON.parse(s);
      const qrToken = obj.qrToken || obj.qr_token;
      if (typeof qrToken === 'string' && qrToken.trim()) return { qrToken: qrToken.trim() };
    } catch {
      // ignore
    }
  }

  // 2) token-only：qr:<token>
  if (s.toLowerCase().startsWith('qr:')) {
    const token = s.slice(3).trim();
    if (token) return { qrToken: token };
  }

  // 爆改阶段不再兼容旧二维码格式
  return null;
}

const ScanScreen = () => {
  const { t } = useI18n();

  const navigation = useNavigation<Nav>();
  const [manual, setManual] = useState('');
  const [scanned, setScanned] = useState(false);

  const [permission, requestPermission] = useCameraPermissions();
  const hasPermission = permission?.granted === true;

  const canUseCamera = Platform.OS !== 'web';

  const hint = useMemo(() => {
    return 'Formato: qr:<token> o JSON {"qrToken":"..."}';
  }, []);

  const goToProcess = (payload: string) => {
    const parsed = parseQrPayload(payload);
    if (!parsed) {
      Alert.alert(t.scan.invalidQr, t.scan.invalidQrDetail);
      return;
    }
    navigation.navigate('ChargingProcess', {
      qrToken: parsed.qrToken,
    });
  };

  return (
    <Screen contentStyle={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>{t.scan.title}</Text>
        <Text style={styles.subTitle}>{t.scan.subtitle}</Text>
      </View>

      {(!canUseCamera || !hasPermission) && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{t.scan.manualTitle}</Text>
          <Text style={styles.cardHint}>{hint}</Text>
          <TextField
            value={manual}
            onChangeText={setManual}
            placeholder={t.scan.placeholder}
            autoCapitalize="none"
          />
          <View style={styles.row}>
            {canUseCamera && !hasPermission && (
              <Button title={t.scan.requestCamera} variant="secondary" onPress={requestPermission} style={styles.action} />
            )}
            <Button title={t.scan.start} onPress={() => goToProcess(manual)} style={styles.action} />
          </View>
        </View>
      )}

      {/* Native camera */}
      {canUseCamera && hasPermission && (
        <View style={styles.cameraWrap}>
          <CameraView
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
    </Screen>
  );
};

const styles = StyleSheet.create({
  container: { padding: spacing.md },
  header: { marginBottom: spacing.lg },
  title: { fontSize: typography.title, fontWeight: typography.bold, color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, lineHeight: 20 },

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
