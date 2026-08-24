/**
 * Google Maps 组件（iOS/Android）
 * - 基于 react-native-maps
 */
import React, { useMemo } from 'react';
import { Platform, StyleSheet } from 'react-native';
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
  center?: { latitude: number; longitude: number };
  zoomDelta?: number;
  markers?: MapMarker[];
  onMarkerPress?: (marker: MapMarker) => void;
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
});

export default GoogleMapView;
