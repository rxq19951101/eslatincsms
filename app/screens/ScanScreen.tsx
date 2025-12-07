/**
 * 本文件为 Scan 页面：使用 expo-camera 实现真实扫码。
 * 仅用于本地测试与演示。
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { StackActions, useFocusEffect } from '@react-navigation/native';

type ScanScreenProps = {
  navigation: any;
  rootNavigation?: any;
};

export default function ScanScreen({ navigation, rootNavigation }: ScanScreenProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const navigatingRef = useRef(false);

  useEffect(() => {
    // 请求相机权限
    if (permission && !permission.granted) {
      requestPermission();
    }
  }, [permission]);

  useFocusEffect(
    useCallback(() => {
      // 页面获得焦点时重置状态并激活相机
      setScanned(false);
      setIsActive(true);
      navigatingRef.current = false;

      return () => {
        // 页面离开时暂停相机，避免黑屏或摄像头占用
        setIsActive(false);
      };
    }, [])
  );

  const navigateToSession = (chargerId: string) => {
    if (navigatingRef.current) {
      console.log('[Scan] 已在跳转中，忽略重复点击');
      return;
    }
    navigatingRef.current = true;
    console.log('[Scan] navigateToSession called, chargerId=', chargerId);
    const pushToSession = StackActions.push('Session', { chargerId });

    if (rootNavigation?.dispatch) {
      console.log('[Scan] 使用 rootNavigation.dispatch 推入 Session');
      rootNavigation.dispatch(pushToSession);
    } else {
      const parentNav = navigation.getParent?.();
      if (parentNav?.dispatch) {
        console.log('[Scan] 尝试使用 parentNav.dispatch 推入 Session');
        parentNav.dispatch(pushToSession);
      } else if (navigation?.dispatch) {
        console.log('[Scan] 使用当前 navigation.dispatch 推入 Session');
        navigation.dispatch(pushToSession);
      } else {
        console.log('[Scan] 未找到可用导航器，放弃跳转');
        navigatingRef.current = false;
        return;
      }
    }

    // 跳转发起后重置相机状态，避免残留提示
    setScanned(false);
    setIsActive(false);

    // 500ms 后允许重新点击（防止 dispatch 被拒绝时卡住）
    setTimeout(() => {
      navigatingRef.current = false;
    }, 500);
  };

  const handleBarCodeScanned = ({ type, data }: { type: string; data: string }) => {
    if (scanned) return;

    setScanned(true);
    setIsActive(false);

    // 二维码格式：CP-XXXX 或者直接是充电桩ID
    let chargerId = data.trim();
    
    // 如果是URL格式，尝试提取ID
    if (data.startsWith('http')) {
      const match = data.match(/cp[=-]?(\w+)/i);
      if (match) {
        chargerId = `CP-${match[1]}`;
      }
    }

    console.log('[Scan] 扫码成功，chargerId=', chargerId);

    Alert.alert(
      '扫码成功',
      `扫描到充电桩: ${chargerId}`,
      [
        {
          text: '确定',
          onPress: () => {
            console.log('[Scan] 点击确定，准备跳转 Session');
            navigateToSession(chargerId);
          },
        },
        {
          text: '取消',
          onPress: () => {
            console.log('[Scan] 点击取消，恢复扫码');
            setScanned(false);
            setIsActive(true);
          },
          style: 'cancel',
        },
      ]
    );
  };

  if (!permission) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#fff" />
        <Text style={styles.loadingText}>正在请求相机权限...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>需要相机权限才能扫码</Text>
        <TouchableOpacity style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>授权相机权限</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {isActive ? (
        <CameraView
          style={styles.camera}
          facing="back"
          onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
          barcodeScannerSettings={{
            barcodeTypes: ['qr', 'code128', 'ean13'],
          }}
        >
          <View style={styles.overlay}>
            <View style={styles.scanArea}>
              <View style={styles.scanCorner}>
                <View style={[styles.corner, styles.topLeft]} />
                <View style={[styles.corner, styles.topRight]} />
                <View style={[styles.corner, styles.bottomLeft]} />
                <View style={[styles.corner, styles.bottomRight]} />
              </View>
            </View>
            <Text style={styles.hint}>将充电桩二维码放入框内</Text>
          </View>
        </CameraView>
      ) : (
        <View style={[styles.camera, styles.cameraPaused]}>
          <Text style={styles.pausedText}>相机已暂停</Text>
        </View>
      )}

      <TouchableOpacity
        style={styles.buttonSecondary}
        onPress={() => navigation.goBack()}
      >
        <Text style={styles.buttonTextSecondary}>返回</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  cameraPaused: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#000',
  },
  pausedText: {
    color: '#fff',
    fontSize: 16,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanArea: {
    width: 250,
    height: 250,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanCorner: {
    width: '100%',
    height: '100%',
  },
  corner: {
    position: 'absolute',
    width: 30,
    height: 30,
    borderColor: '#007AFF',
    borderWidth: 3,
  },
  topLeft: {
    top: 0,
    left: 0,
    borderRightWidth: 0,
    borderBottomWidth: 0,
  },
  topRight: {
    top: 0,
    right: 0,
    borderLeftWidth: 0,
    borderBottomWidth: 0,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderRightWidth: 0,
    borderTopWidth: 0,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderLeftWidth: 0,
    borderTopWidth: 0,
  },
  hint: {
    color: '#fff',
    fontSize: 16,
    marginTop: 80,
    textAlign: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  loadingText: {
    color: '#fff',
    marginTop: 16,
    fontSize: 16,
  },
  errorText: {
    color: '#fff',
    fontSize: 18,
    marginBottom: 24,
    textAlign: 'center',
  },
  button: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginTop: 24,
  },
  buttonSecondary: {
    position: 'absolute',
    bottom: 32,
    left: 16,
    right: 16,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#fff',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  buttonTextSecondary: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
});

