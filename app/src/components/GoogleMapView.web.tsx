/**
 * Web：不加载 react-native-maps（该库仅原生）。占位以便登录等非地图流程可在浏览器调试。
 */
import React from 'react';
import { View, StyleSheet, Text } from 'react-native';
import { useI18n } from '../i18n';

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

export const GoogleMapView: React.FC<GoogleMapViewProps> = ({ style }) => {
  const { t } = useI18n();
  return (
    <View style={[styles.webFallback, style]}>
      <Text style={styles.webTitle}>{t.home.mapUnavailable}</Text>
      <Text style={styles.webHint}>{t.home.mapUnavailableHint}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  webFallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E5E7EB',
    padding: 16,
  },
  webTitle: { color: '#374151', fontWeight: '700', marginBottom: 8, textAlign: 'center' },
  webHint: { color: '#6B7280', fontSize: 13, textAlign: 'center' },
});

export default GoogleMapView;
