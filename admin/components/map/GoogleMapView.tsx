'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader } from '@googlemaps/js-api-loader';

interface GoogleMapViewProps {
  center?: { lat: number; lng: number };
  markers?: Array<{ lat: number; lng: number; title?: string }>;
  onClick?: (lat: number, lng: number) => void;
  height?: string;
  zoom?: number;
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

export default function GoogleMapView(props: GoogleMapViewProps) {
  const {
    center = { lat: 4.6097, lng: -74.0817 }, // 默认波哥大
    markers = [],
    onClick,
    height = '400px',
    zoom = 13
  } = props;

  const mapRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 初始化 Google Maps
  useEffect(() => {
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
          disableDefaultUI: false,
          zoomControl: true,
          mapTypeControl: false,
          scaleControl: true,
          streetViewControl: false,
          rotateControl: false,
          fullscreenControl: true
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
      })
      .catch((err) => {
        console.error('Google Maps 加载失败:', err);
        setError('地图加载失败，请检查网络连接');
        setLoading(false);
      });
  }, []);

  // 更新地图中心
  useEffect(() => {
    if (googleMapRef.current && center) {
      googleMapRef.current.setCenter(center);
    }
  }, [center.lat, center.lng]);

  // 更新标记点
  useEffect(() => {
    if (!googleMapRef.current) return;

    // 清除旧标记
    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = [];

    // 添加新标记
    markers.forEach((markerData) => {
      const marker = new google.maps.Marker({
        position: { lat: markerData.lat, lng: markerData.lng },
        map: googleMapRef.current!,
        title: markerData.title,
        animation: google.maps.Animation.DROP
      });
      markersRef.current.push(marker);
    });
  }, [markers]);

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
