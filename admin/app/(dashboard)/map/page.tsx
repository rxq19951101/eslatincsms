'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Map as MapIcon } from 'lucide-react';

// 动态导入 Leaflet（仅在客户端加载）
const MapComponent = dynamic(() => import('@/components/map/MapView'), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] flex items-center justify-center bg-slate-800 rounded-lg">
      <div className="text-slate-400">地图加载中...</div>
    </div>
  ),
});

export default function MapPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">地图视图</h1>
        <p className="text-slate-400 mt-1">在地图上查看所有充电桩位置</p>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <MapIcon className="h-5 w-5" />
            充电桩地图
          </CardTitle>
        </CardHeader>
        <CardContent>
          <MapComponent />
        </CardContent>
      </Card>
    </div>
  );
}