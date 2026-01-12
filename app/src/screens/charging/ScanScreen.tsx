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
  TouchableOpacity,
  TextInput,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import { CameraView, useCameraPermissions } from 'expo-camera';

import { COLORS } from '../../constants/config';
import type { RootStackParamList } from '../../types';

type Nav = StackNavigationProp<RootStackParamList>;

type ParsedQr = { chargePointId: string; connectorId?: number };

function parseQrPayload(raw: string): ParsedQr | null {
  const s = (raw || '').trim();
  if (!s) return null;

  // 1) JSON: {"chargePointId":"...","connectorId":2} 或 snake_case
  if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
    try {
      const obj: any = JSON.parse(s);
      const chargePointId =
        obj.chargePointId || obj.charge_point_id || obj.chargePointID || obj.charge_pointId;
      const connectorId = obj.connectorId ?? obj.connector_id;
      if (typeof chargePointId === 'string' && chargePointId.trim()) {
        return {
          chargePointId: chargePointId.trim(),
          connectorId: typeof connectorId === 'number' ? connectorId : undefined,
        };
      }
    } catch {
      // ignore
    }
  }

  // 2) 形如：CP_SITE_001_01#2
  if (s.includes('#')) {
    const [id, conn] = s.split('#');
    const connectorId = Number(conn);
    if (id?.trim()) return { chargePointId: id.trim(), connectorId: Number.isFinite(connectorId) ? connectorId : undefined };
  }

  // 3) 形如：CP_SITE_001_01?connector=2
  if (s.includes('?')) {
    const [id, qs] = s.split('?');
    const m = qs?.match(/connector(?:Id)?=(\d+)/i);
    const connectorId = m ? Number(m[1]) : undefined;
    if (id?.trim()) return { chargePointId: id.trim(), connectorId };
  }

  // 4) 兜底：纯 charge_point_id
  return { chargePointId: s };
}

const ScanScreen = () => {
  const navigation = useNavigation<Nav>();
  const [manual, setManual] = useState('');
  const [scanned, setScanned] = useState(false);

  const [permission, requestPermission] = useCameraPermissions();
  const hasPermission = permission?.granted === true;

  const canUseCamera = Platform.OS !== 'web';

  const hint = useMemo(() => {
    return '二维码内容必须包含 charge_point_id + connector_id（一个二维码=一个connector）：\n- CP_SITE_001_01#2\n- CP_SITE_001_01?connector=2\n- JSON {\"chargePointId\":\"...\",\"connectorId\":2}';
  }, []);

  const goToProcess = (payload: string) => {
    const parsed = parseQrPayload(payload);
    if (!parsed) {
      Alert.alert('二维码无效', '请确认二维码内容包含 charge_point_id 和 connector_id');
      return;
    }
    if (typeof parsed.connectorId !== 'number' || !Number.isFinite(parsed.connectorId) || parsed.connectorId <= 0) {
      Alert.alert('二维码无效', '该二维码未解析出 connector_id（一个二维码应对应一个 connector）');
      return;
    }
    navigation.navigate('ChargingProcess', {
      chargePointId: parsed.chargePointId,
      connectorId: parsed.connectorId,
    });
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>扫码充电</Text>
        <Text style={styles.subTitle}>对准充电桩二维码，自动识别并进入充电流程</Text>
      </View>

      {/* Web fallback / 权限引导 */}
      {(!canUseCamera || !hasPermission) && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>手动输入（Web/无权限时）</Text>
          <Text style={styles.cardHint}>{hint}</Text>
          <TextInput
            value={manual}
            onChangeText={setManual}
            placeholder="粘贴二维码内容…"
            style={styles.input}
            autoCapitalize="none"
          />
          <View style={styles.row}>
            {canUseCamera && !hasPermission && (
              <TouchableOpacity style={[styles.btn, styles.secondary]} onPress={requestPermission}>
                <Text style={styles.secondaryText}>请求相机权限</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity style={[styles.btn, styles.primary]} onPress={() => goToProcess(manual)}>
              <Text style={styles.primaryText}>进入充电</Text>
            </TouchableOpacity>
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
            <Text style={styles.overlayText}>对准二维码</Text>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.BACKGROUND, padding: 16 },
  header: { marginBottom: 12 },
  title: { fontSize: 22, fontWeight: '800', color: COLORS.TEXT_PRIMARY },
  subTitle: { marginTop: 6, color: COLORS.TEXT_SECONDARY, lineHeight: 20 },

  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
  },
  cardTitle: { fontSize: 16, fontWeight: '800', color: COLORS.TEXT_PRIMARY, marginBottom: 8 },
  cardHint: { color: COLORS.TEXT_SECONDARY, lineHeight: 18, marginBottom: 12 },
  input: {
    height: 44,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    paddingHorizontal: 12,
    backgroundColor: '#FFFFFF',
  },
  row: { flexDirection: 'row', marginTop: 12 },
  btn: { flex: 1, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: COLORS.PRIMARY, marginLeft: 10 },
  primaryText: { color: '#FFFFFF', fontWeight: '800' },
  secondary: { backgroundColor: '#E5E7EB' },
  secondaryText: { color: COLORS.TEXT_PRIMARY, fontWeight: '800' },

  cameraWrap: {
    flex: 1,
    borderRadius: 16,
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
    fontWeight: '800',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 6,
  },
});

export default ScanScreen;

