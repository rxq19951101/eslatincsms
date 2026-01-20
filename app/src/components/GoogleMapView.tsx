/**
 * Google Maps 组件（iOS/Android）
 * - 基于 react-native-maps
 * - 用于替换 Mapbox 实现
 */
 
import React, { useMemo } from 'react';
import { Platform, View, StyleSheet, Text } from 'react-native';
import MapView, { Marker, PROVIDER_GOOGLE, Region } from 'react-native-maps';
import { MAP_CONFIG } from '../constants/config';

export type MapMarker = {
  id: string;
  latitude: number;
  longitude: number;
  title?: string;
  description?: string;
  status?: string;
  available?: number;
};

export interface GoogleMapViewProps {
  /** 初始中心点（经纬度） */
  center?: { latitude: number; longitude: number };
  /** 初始缩放：用 delta 近似 */
  zoomDelta?: number;
  /** markers */
  markers?: MapMarker[];
  /** 点击 marker */
  onMarkerPress?: (marker: MapMarker) => void;
  /** 是否显示用户位置 */
  showsUserLocation?: boolean;
  style?: any;
}

function getMarkerPinColor(status?: string, available?: number): string {
  const s = (status || '').toLowerCase();
  if (s === 'offline' || s === 'unavailable') return MAP_CONFIG.MARKER_COLORS.OFFLINE;
  if (typeof available === 'number' && available > 0) return MAP_CONFIG.MARKER_COLORS.AVAILABLE;
  if (typeof available === 'number' && available === 0) return MAP_CONFIG.MARKER_COLORS.OCCUPIED;
  return MAP_CONFIG.MARKER_COLORS.UNKNOWN;
}

export const GoogleMapView: React.FC<GoogleMapViewProps> = ({
  center,
  zoomDelta = 0.05,
  markers = [],
  onMarkerPress,
  showsUserLocation = true,
  style,
}) => {
  // 仅 iOS/Android 支持；你已确认 web 不要求可用
  if (Platform.OS === 'web') {
    return (
      <View style={[styles.webFallback, style]}>
        <Text style={styles.webTitle}>地图仅在移动端可用</Text>
      </View>
    );
  }

  // 兼容：Android 使用 Google Provider；iOS 在 Expo Go 场景下通常只能稳定使用默认(Apple Maps) provider
  const provider = Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined;

  const initialRegion: Region = useMemo(() => {
    const latitude = center?.latitude ?? MAP_CONFIG.DEFAULT_LATITUDE;
    const longitude = center?.longitude ?? MAP_CONFIG.DEFAULT_LONGITUDE;
    return {
      latitude,
      longitude,
      latitudeDelta: zoomDelta,
      longitudeDelta: zoomDelta,
    };
  }, [center?.latitude, center?.longitude, zoomDelta]);

  return (
    <MapView
      provider={provider}
      style={[styles.map, style]}
      initialRegion={initialRegion}
      showsUserLocation={showsUserLocation}
      showsMyLocationButton
      toolbarEnabled
      rotateEnabled={false}
    >
      {markers
        .filter((m) => Number.isFinite(m.latitude) && Number.isFinite(m.longitude))
        .map((m) => (
          <Marker
            key={m.id}
            coordinate={{ latitude: m.latitude, longitude: m.longitude }}
            title={m.title}
            description={m.description}
            pinColor={getMarkerPinColor(m.status, m.available)}
            onPress={() => onMarkerPress?.(m)}
          />
        ))}
    </MapView>
  );
};

const styles = StyleSheet.create({
  map: { flex: 1 },
  webFallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E5E7EB',
  },
  webTitle: { color: '#374151', fontWeight: '700' },
});

export default GoogleMapView;

