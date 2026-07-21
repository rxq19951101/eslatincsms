/**
 * 地图视图组件
 * 使用 @rnmapbox/maps 显示交互式地图
 */

import React, { useRef, useEffect } from 'react';
import { View, StyleSheet, Platform, Text } from 'react-native';
import { MAP_CONFIG } from '../constants/config';
import { useI18n } from '../i18n';
import Icon from './ui/Icon';

// 仅在非Web平台导入Mapbox GL
let MapboxGL: any = null;
if (Platform.OS !== 'web') {
  MapboxGL = require('@rnmapbox/maps').default;
  // 设置Mapbox访问令牌
  MapboxGL.setAccessToken(MAP_CONFIG.MAPBOX_ACCESS_TOKEN);
}

interface MapViewProps {
  children?: React.ReactNode;
  centerCoordinate?: [number, number];
  zoomLevel?: number;
  onMapReady?: () => void;
  onRegionDidChange?: (feature: any) => void;
  style?: any;
}

const CustomMapView: React.FC<MapViewProps> = ({
  children,
  centerCoordinate = [MAP_CONFIG.DEFAULT_LONGITUDE, MAP_CONFIG.DEFAULT_LATITUDE],
  zoomLevel = MAP_CONFIG.DEFAULT_ZOOM,
  onMapReady,
  onRegionDidChange,
  style,
}) => {
  const { t } = useI18n();
  const mapRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);

  useEffect(() => {
    // 地图加载完成后的初始化
    if (onMapReady) {
      onMapReady();
    }
  }, [onMapReady]);

  // Web平台降级处理
  if (Platform.OS === 'web' || !MapboxGL) {
    return (
      <View style={[styles.webFallback, style]}>
        <View style={styles.webPlaceholder}>
          <Icon name="map-outline" size={64} color="#708596" style={styles.webIcon} />
          <Text style={styles.webSubtext}>{t.home.mapWebLimited}</Text>
        </View>
        {children}
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <MapboxGL.MapView
        ref={mapRef}
        style={styles.map}
        styleURL={MAP_CONFIG.MAPBOX_STYLE_URL}
        onDidFinishLoadingMap={onMapReady}
        onRegionDidChange={onRegionDidChange}
        compassEnabled={true}
        compassViewPosition={3} // 右上角
        logoEnabled={false}
        attributionEnabled={true}
        attributionPosition={{ bottom: 8, left: 8 }}
      >
        <MapboxGL.Camera
          ref={cameraRef}
          zoomLevel={zoomLevel}
          centerCoordinate={centerCoordinate}
          animationMode="flyTo"
          animationDuration={2000}
        />

        {/* 用户位置指示器 */}
        <MapboxGL.UserLocation
          visible={true}
          showsUserHeadingIndicator={true}
        />

        {children}
      </MapboxGL.MapView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  map: {
    flex: 1,
  },
  webFallback: {
    flex: 1,
    backgroundColor: '#E5E7EB',
    position: 'relative',
  },
  webPlaceholder: {
    position: 'absolute',
    top: '40%',
    left: 0,
    right: 0,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  webIcon: {
    marginBottom: 16,
  },
  webSubtext: {
    fontSize: 16,
    color: '#6B7280',
    textAlign: 'center',
    lineHeight: 24,
    paddingHorizontal: 40,
  },
});

export default CustomMapView;
