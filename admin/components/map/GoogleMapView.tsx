'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { Loader } from '@googlemaps/js-api-loader';
import { useI18n } from '@/lib/i18n';

interface GoogleMapViewProps {
  center?: { lat: number; lng: number };
  markers?: Array<{ lat: number; lng: number; title?: string }>;
  onClick?: (lat: number, lng: number) => void;
  height?: string;
  zoom?: number;
  /** 是否禁用交互（缩放、拖拽等），用于只读展示模式 */
  disableInteraction?: boolean;
}

/** Advanced Marker 需要 mapId；可在 Cloud Console 创建或使用官方示例 ID */
const DEFAULT_MAP_ID = 'DEMO_MAP_ID';

type MarkerPoint = { lat: number; lng: number; title?: string };

export default function GoogleMapView(props: GoogleMapViewProps) {
  const {
    center = { lat: 4.6097, lng: -74.0817 },
    markers = [],
    onClick,
    height = '400px',
    zoom = 13,
    disableInteraction = false
  } = props;
  const { locale, t } = useI18n();

  const mapRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.marker.AdvancedMarkerElement[]>([]);
  const mapInitStartedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mapId =
    typeof process !== 'undefined'
      ? process.env.NEXT_PUBLIC_GOOGLE_MAP_ID || DEFAULT_MAP_ID
      : DEFAULT_MAP_ID;

  const clearAndAddMarkers = useCallback(async (map: google.maps.Map, list: MarkerPoint[]) => {
    const { AdvancedMarkerElement, PinElement } = (await google.maps.importLibrary(
      'marker'
    )) as google.maps.MarkerLibrary;

    markersRef.current.forEach((m) => {
      m.map = null;
    });
    markersRef.current = [];

    if (!list?.length) return;

    for (const markerData of list) {
      if (!markerData || typeof markerData.lat !== 'number' || typeof markerData.lng !== 'number') {
        continue;
      }

      const pin = new PinElement({
        background: '#ef4444',
        borderColor: '#ffffff',
        glyphColor: '#ffffff',
        scale: 1.15
      });

      const adv = new AdvancedMarkerElement({
        map,
        position: { lat: markerData.lat, lng: markerData.lng },
        title: markerData.title || t('充电站位置'),
        content: pin.element,
        zIndex: 1000
      });

      if (markerData.title) {
        const infoWindow = new google.maps.InfoWindow({
          content: `<div style="padding: 8px; font-weight: bold; color: #1f2937;">${markerData.title}</div>`
        });
        adv.addListener('click', () => {
          infoWindow.open({ map, anchor: adv });
        });
      }

      markersRef.current.push(adv);
    }
  }, [t]);

  useEffect(() => {
    if (googleMapRef.current) return;
    if (mapInitStartedRef.current) return;
    if (!center) return;

    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      setError(t('Google Maps API 密钥未配置'));
      setLoading(false);
      return;
    }

    mapInitStartedRef.current = true;

    const loader = new Loader({
      apiKey,
      version: 'weekly',
      libraries: ['places'],
      language: locale === 'es' ? 'es' : locale === 'en' ? 'en' : 'zh-CN',
      region: 'CO'
    });

    loader
      .load()
      .then(async () => {
        if (!mapRef.current) return;

        const map = new google.maps.Map(mapRef.current, {
          center,
          zoom,
          mapId,
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

        if (onClick) {
          map.addListener('click', (e: google.maps.MapMouseEvent) => {
            if (e.latLng) {
              onClick(e.latLng.lat(), e.latLng.lng());
            }
          });
        }

        await clearAndAddMarkers(map, markers);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Google Maps 加载失败:', err);
        mapInitStartedRef.current = false;
        setError(t('地图加载失败，请检查网络连接、项目结算账号以及 Maps JavaScript API 是否启用'));
        setLoading(false);
      });
    // markers / zoom 变更由下方 effect 处理，勿写入依赖以免重复初始化地图
  }, [center?.lat, center?.lng, onClick, disableInteraction, clearAndAddMarkers, mapId, locale]);

  useEffect(() => {
    if (googleMapRef.current && center) {
      googleMapRef.current.setCenter(center);
    }
  }, [center?.lat, center?.lng]);

  useEffect(() => {
    if (googleMapRef.current) {
      googleMapRef.current.setZoom(zoom);
    }
  }, [zoom]);

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

  useEffect(() => {
    const map = googleMapRef.current;
    if (!map) return;
    void clearAndAddMarkers(map, markers);
  }, [markers, clearAndAddMarkers]);

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
          <div className="text-slate-400 text-sm">{t('加载地图中...')}</div>
        </div>
      )}
    </div>
  );
}
