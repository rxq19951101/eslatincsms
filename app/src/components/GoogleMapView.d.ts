import type React from 'react';
import type { StyleProp, ViewStyle } from 'react-native';

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
  style?: StyleProp<ViewStyle>;
}

declare const GoogleMapView: React.FC<GoogleMapViewProps>;
export default GoogleMapView;

