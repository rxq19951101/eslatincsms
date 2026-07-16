'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Map as MapIcon } from 'lucide-react';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import type { SiteListItem } from '@/types';

const GoogleMapView = dynamic(() => import('@/components/map/GoogleMapView'), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] flex items-center justify-center bg-slate-800 rounded-lg">
      <div className="text-slate-400">地图加载中...</div>
    </div>
  ),
});

const fetcher = (url: string) => apiGet<SiteListItem[]>(url);

export default function MapPage() {
  const { data: sites, isLoading } = useSWR(API_ENDPOINTS.SITES, fetcher, {
    refreshInterval: 30000,
  });

  const markers = useMemo(
    () =>
      (sites || []).map((s) => ({
        lat: s.latitude,
        lng: s.longitude,
        title: `${s.name} (${s.charge_points_count} 桩)`,
      })),
    [sites]
  );

  const center = useMemo(() => {
    if (markers.length > 0) {
      return { lat: markers[0].lat, lng: markers[0].lng };
    }
    return { lat: 4.6097, lng: -74.0817 };
  }, [markers]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">地图视图</h1>
        <p className="text-slate-400 mt-1">
          在 Google 地图上查看各站点位置（数据来自站点列表）
        </p>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <MapIcon className="h-5 w-5" />
            站点地图
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && !sites ? (
            <div className="h-[600px] flex items-center justify-center bg-slate-900/50 rounded-lg text-slate-400">
              加载站点数据…
            </div>
          ) : (
            <GoogleMapView height="600px" center={center} markers={markers} zoom={12} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
