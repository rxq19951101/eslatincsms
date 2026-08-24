/**
 * 充电站地图标记组件
 */

import React from 'react';
import { View, Text, StyleSheet, Platform } from 'react-native';
import { MAP_CONFIG } from '../constants/config';
import { Charger } from '../api/chargers';
import Icon from './ui/Icon';

// 仅在非Web平台导入Mapbox GL
let MapboxGL: any = null;
if (Platform.OS !== 'web') {
  MapboxGL = require('@rnmapbox/maps').default;
}

interface ChargerMarkerProps {
  charger: Charger;
  onPress: (charger: Charger) => void;
}

/**
 * 根据充电站状态获取标记颜色
 */
const getMarkerColor = (status: string, available?: number): string => {
  if (status === 'Offline' || status === 'Unavailable') {
    return MAP_CONFIG.MARKER_COLORS.OFFLINE;
  }
  if (available !== undefined && available > 0) {
    return MAP_CONFIG.MARKER_COLORS.AVAILABLE;
  }
  if (available === 0) {
    return MAP_CONFIG.MARKER_COLORS.OCCUPIED;
  }
  return MAP_CONFIG.MARKER_COLORS.UNKNOWN;
};

/**
 * 单个充电站标记
 */
const ChargerMarker: React.FC<ChargerMarkerProps> = ({ charger, onPress }) => {
  if (!charger.latitude || !charger.longitude || Platform.OS === 'web' || !MapboxGL) {
    return null;
  }

  const markerColor = getMarkerColor(charger.status, charger.available_connectors);
  const coordinate: [number, number] = [charger.longitude, charger.latitude];

  return (
    <MapboxGL.PointAnnotation
      id={`charger-${charger.id}`}
      coordinate={coordinate}
      onSelected={() => onPress(charger)}
    >
      <View style={styles.markerContainer}>
        <View style={[styles.marker, { backgroundColor: markerColor }]}>
          <Icon name="flash" size={20} color="#FFFFFF" />
        </View>
        {charger.available_connectors !== undefined && (
          <View style={[styles.badge, { backgroundColor: markerColor }]}>
            <Text style={styles.badgeText}>
              {charger.available_connectors}
            </Text>
          </View>
        )}
      </View>
    </MapboxGL.PointAnnotation>
  );
};

/**
 * 充电站标记集合（用于批量渲染）
 */
interface ChargerMarkersProps {
  chargers: Charger[];
  onMarkerPress: (charger: Charger) => void;
}

export const ChargerMarkers: React.FC<ChargerMarkersProps> = ({
  chargers,
  onMarkerPress,
}) => {
  return (
    <>
      {chargers.map((charger) => (
        <ChargerMarker
          key={charger.id}
          charger={charger}
          onPress={onMarkerPress}
        />
      ))}
    </>
  );
};

/**
 * 使用GeoJSON和聚合的高性能标记渲染
 */
interface ClusteredMarkersProps {
  chargers: Charger[];
  onMarkerPress: (charger: Charger) => void;
}

export const ClusteredMarkers: React.FC<ClusteredMarkersProps> = ({
  chargers,
  onMarkerPress,
}) => {
  // Web平台不渲染标记
  if (Platform.OS === 'web' || !MapboxGL) {
    return null;
  }

  // 转换为GeoJSON格式
  const geoJSON = {
    type: 'FeatureCollection' as const,
    features: chargers
      .filter((c) => c.latitude && c.longitude)
      .map((charger) => ({
        type: 'Feature' as const,
        id: charger.id,
        geometry: {
          type: 'Point' as const,
          coordinates: [charger.longitude!, charger.latitude!],
        },
        properties: {
          id: charger.id,
          status: charger.status,
          available: charger.available_connectors || 0,
          total: charger.total_connectors || 0,
          color: getMarkerColor(charger.status, charger.available_connectors),
        },
      })),
  };

  const handleFeaturePress = (event: any) => {
    const feature = event.features[0];
    if (feature && feature.properties.id) {
      const charger = chargers.find((c) => c.id === feature.properties.id);
      if (charger) {
        onMarkerPress(charger);
      }
    }
  };

  return (
    <MapboxGL.ShapeSource
      id="chargers-source"
      shape={geoJSON}
      cluster={true}
      clusterRadius={MAP_CONFIG.CLUSTER_RADIUS}
      clusterMaxZoomLevel={14}
      onPress={handleFeaturePress}
    >
      {/* 聚合圆圈 */}
      <MapboxGL.CircleLayer
        id="clusters"
        filter={['has', 'point_count']}
        style={{
          circleColor: MAP_CONFIG.MARKER_COLORS.AVAILABLE,
          circleRadius: [
            'step',
            ['get', 'point_count'],
            20, // 默认半径
            10, 25, // 10个点时半径25
            50, 30, // 50个点时半径30
          ],
          circleOpacity: 0.8,
          circleStrokeWidth: 2,
          circleStrokeColor: '#FFFFFF',
        }}
      />

      {/* 聚合数字 */}
      <MapboxGL.SymbolLayer
        id="cluster-count"
        filter={['has', 'point_count']}
        style={{
          textField: ['get', 'point_count'],
          textSize: 14,
          textColor: '#FFFFFF',
          textFont: ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
        }}
      />

      {/* 单个标记 */}
      <MapboxGL.CircleLayer
        id="unclustered-point"
        filter={['!', ['has', 'point_count']]}
        style={{
          circleColor: ['get', 'color'],
          circleRadius: 12,
          circleStrokeWidth: 2,
          circleStrokeColor: '#FFFFFF',
        }}
      />

      {/* 可用数量标签 */}
      <MapboxGL.SymbolLayer
        id="unclustered-label"
        filter={['!', ['has', 'point_count']]}
        style={{
          textField: ['get', 'available'],
          textSize: 10,
          textColor: '#FFFFFF',
          textFont: ['DIN Offc Pro Bold', 'Arial Unicode MS Bold'],
        }}
      />
    </MapboxGL.ShapeSource>
  );
};

const styles = StyleSheet.create({
  markerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  marker: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 3,
    borderColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    elevation: 5,
  },
  badge: {
    position: 'absolute',
    top: -5,
    right: -5,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
  badgeText: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
});

export default ChargerMarker;
