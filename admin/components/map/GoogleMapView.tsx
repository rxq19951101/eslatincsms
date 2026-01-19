'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader } from '@googlemaps/js-api-loader';

interface GoogleMapViewProps {
  center?: { lat: number; lng: number };
  markers?: Array<{ lat: number; lng: number; title?: string }>;
  onClick?: (lat: number, lng: number) => void;
  height?: string;
  zoom?: number;
  /** 是否禁用交互（缩放、拖拽等），用于只读展示模式 */
  disableInteraction?: boolean;
}

// Google Maps 暗色主题样式
const darkModeStyles: google.maps.MapTypeStyle[] = [
  { elementType: 'geometry', stylers: [{ color: '#212121' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#212121' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#746855' }] },
  {
    featureType: 'administrative.locality',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#d59563' }]
  },
  {
    featureType: 'poi',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#d59563' }]
  },
  {
    featureType: 'poi.park',
    elementType: 'geometry',
    stylers: [{ color: '#263c3f' }]
  },
  {
    featureType: 'poi.park',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#6b9a76' }]
  },
  {
    featureType: 'road',
    elementType: 'geometry',
    stylers: [{ color: '#38414e' }]
  },
  {
    featureType: 'road',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#212a37' }]
  },
  {
    featureType: 'road',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#9ca5b3' }]
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry',
    stylers: [{ color: '#746855' }]
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#1f2835' }]
  },
  {
    featureType: 'road.highway',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#f3d19c' }]
  },
  {
    featureType: 'transit',
    elementType: 'geometry',
    stylers: [{ color: '#2f3948' }]
  },
  {
    featureType: 'transit.station',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#d59563' }]
  },
  {
    featureType: 'water',
    elementType: 'geometry',
    stylers: [{ color: '#17263c' }]
  },
  {
    featureType: 'water',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#515c6d' }]
  },
  {
    featureType: 'water',
    elementType: 'labels.text.stroke',
    stylers: [{ color: '#17263c' }]
  }
];

// 创建自定义红色标记图标（SVG base64）- 移到组件外部
const createCustomMarkerIcon = (): google.maps.Icon => {
  // 使用 SVG 创建红色充电桩标记图标
  const svgMarker = `
    <svg width="40" height="50" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 0C9 0 0 9 0 20c0 11 20 30 20 30s20-19 20-30c0-11-9-20-20-20z" fill="#ef4444" stroke="#ffffff" stroke-width="2"/>
      <text x="20" y="28" font-family="Arial" font-size="16" font-weight="bold" fill="white" text-anchor="middle">⚡</text>
    </svg>
  `;
  return {
    url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svgMarker),
    scaledSize: new google.maps.Size(40, 50),
    anchor: new google.maps.Point(20, 50),
    origin: new google.maps.Point(0, 0)
  };
};

export default function GoogleMapView(props: GoogleMapViewProps) {
  const {
    center = { lat: 4.6097, lng: -74.0817 }, // 默认波哥大
    markers = [],
    onClick,
    height = '400px',
    zoom = 13,
    disableInteraction = false
  } = props;

  const mapRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 初始化 Google Maps（只初始化一次，等待 center 准备好）
  useEffect(() => {
    // 如果地图已经初始化，跳过
    if (googleMapRef.current) return;
    
    // 如果 center 还没准备好，等待
    if (!center) return;

    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      setError('Google Maps API 密钥未配置');
      setLoading(false);
      return;
    }

    const loader = new Loader({
      apiKey,
      version: 'weekly',
      libraries: ['places']
    });

    loader
      .load()
      .then(() => {
        if (!mapRef.current) return;

        // 创建地图
        const map = new google.maps.Map(mapRef.current, {
          center,
          zoom,
          styles: darkModeStyles,
          disableDefaultUI: disableInteraction,
          zoomControl: !disableInteraction,
          mapTypeControl: false,
          scaleControl: !disableInteraction,
          streetViewControl: false,
          rotateControl: false,
          fullscreenControl: !disableInteraction,
          gestureHandling: disableInteraction ? 'none' : 'auto',
          draggable: !disableInteraction,
          scrollwheel: !disableInteraction,
          disableDoubleClickZoom: disableInteraction
        });

        googleMapRef.current = map;

        // 点击地图事件
        if (onClick) {
          map.addListener('click', (e: google.maps.MapMouseEvent) => {
            if (e.latLng) {
              onClick(e.latLng.lat(), e.latLng.lng());
            }
          });
        }

        setLoading(false);
        
        // 地图初始化完成后，立即添加标记（如果已有标记数据）
        if (markers && markers.length > 0) {
          markers.forEach((markerData) => {
            if (markerData && typeof markerData.lat === 'number' && typeof markerData.lng === 'number') {
              const marker = new google.maps.Marker({
                position: { lat: markerData.lat, lng: markerData.lng },
                map: map,
                title: markerData.title || '充电站位置',
                animation: google.maps.Animation.DROP,
                icon: createCustomMarkerIcon(),
                zIndex: 1000,
                optimized: false
              });
              
              if (markerData.title) {
                const infoWindow = new google.maps.InfoWindow({
                  content: `<div style="padding: 8px; font-weight: bold; color: #1f2937;">${markerData.title}</div>`
                });
                marker.addListener('click', () => {
                  infoWindow.open(map, marker);
                });
              }
              
              markersRef.current.push(marker);
            }
          });
        }
      })
      .catch((err) => {
        console.error('Google Maps 加载失败:', err);
        setError('地图加载失败，请检查网络连接');
        setLoading(false);
      });
  }, [center?.lat, center?.lng, onClick, disableInteraction, markers]);

  // 更新地图中心
  useEffect(() => {
    if (googleMapRef.current && center) {
      googleMapRef.current.setCenter(center);
    }
  }, [center?.lat, center?.lng]);

  // 动态更新地图交互性
  useEffect(() => {
    if (!googleMapRef.current) return;
    const map = googleMapRef.current;
    map.setOptions({
      gestureHandling: disableInteraction ? 'none' : 'auto',
      draggable: !disableInteraction,
      scrollwheel: !disableInteraction,
      disableDoubleClickZoom: disableInteraction,
      zoomControl: !disableInteraction,
      scaleControl: !disableInteraction,
      fullscreenControl: !disableInteraction
    });
  }, [disableInteraction]);

  // 更新标记点
  useEffect(() => {
    if (!googleMapRef.current) {
      // 如果地图还没初始化，等待一下
      return;
    }

    // 清除旧标记
    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = [];

    // 如果没有标记数据，直接返回
    if (!markers || markers.length === 0) {
      console.log('[GoogleMapView] 没有标记数据');
      return;
    }

    console.log('[GoogleMapView] 添加标记:', markers);

    // 添加新标记（使用自定义红色充电桩标记）
    markers.forEach((markerData) => {
      if (!markerData || typeof markerData.lat !== 'number' || typeof markerData.lng !== 'number') {
        console.warn('[GoogleMapView] 无效的标记数据:', markerData);
        return;
      }

      try {
        const marker = new google.maps.Marker({
          position: { lat: markerData.lat, lng: markerData.lng },
          map: googleMapRef.current!,
          title: markerData.title || '充电站位置',
          animation: google.maps.Animation.DROP,
          icon: createCustomMarkerIcon(),
          zIndex: 1000, // 确保标记在最上层
          optimized: false // 禁用优化以确保标记始终显示
        });
        
        // 添加信息窗口显示站点名称
        if (markerData.title) {
          const infoWindow = new google.maps.InfoWindow({
            content: `<div style="padding: 8px; font-weight: bold; color: #1f2937;">${markerData.title}</div>`
          });
          marker.addListener('click', () => {
            infoWindow.open(googleMapRef.current!, marker);
          });
        }
        
        markersRef.current.push(marker);
        console.log('[GoogleMapView] 标记已添加:', markerData.title, '位置:', markerData.lat, markerData.lng);
      } catch (error) {
        console.error('[GoogleMapView] 创建标记失败:', error, markerData);
      }
    });
  }, [markers, googleMapRef.current]);

  if (error) {
    return (
      <div
        className="flex items-center justify-center bg-slate-800/50 border border-slate-700 rounded-md"
        style={{ height }}
      >
        <div className="text-center">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative" style={{ height }}>
      <div ref={mapRef} className="w-full h-full rounded-md" />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-800/80 rounded-md">
          <div className="text-slate-400 text-sm">加载地图中...</div>
        </div>
      )}
    </div>
  );
}
