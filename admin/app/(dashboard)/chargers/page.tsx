'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { useRouter } from 'next/navigation';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { ChargePoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Zap, Search, Grid3x3, List, Eye, Power } from 'lucide-react';

const fetcher = (url: string) => apiGet<ChargePoint[]>(url);

export default function ChargersPage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  // 获取充电桩列表
  const { data: chargers, error, isLoading } = useSWR<ChargePoint[]>(
    API_ENDPOINTS.CHARGERS,
    fetcher,
    {
      refreshInterval: 30000, // 30 秒自动刷新
    }
  );

  // 过滤充电桩
  const filteredChargers = chargers?.filter((charger) => {
    const matchesSearch =
      charger.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      charger.vendor?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      charger.model?.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = statusFilter === 'all' || charger.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  // 状态颜色映射
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'available':
        return 'bg-green-500/20 text-green-400 border-green-500/50';
      case 'charging':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/50';
      case 'offline':
        return 'bg-gray-500/20 text-gray-400 border-gray-500/50';
      case 'faulted':
        return 'bg-red-500/20 text-red-400 border-red-500/50';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/50';
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">加载失败，请刷新页面重试</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">充电桩管理</h1>
          <p className="text-slate-400 mt-1">管理所有充电桩设备</p>
        </div>
        <Button
          onClick={() => router.push('/chargers/new')}
          className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
        >
          <Zap className="h-4 w-4 mr-2" />
          添加充电桩
        </Button>
      </div>

      {/* Filters */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                type="text"
                placeholder="搜索充电桩 ID、厂商、型号..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-slate-700/50 border-slate-600 text-slate-200 placeholder:text-slate-500"
              />
            </div>

            {/* Status Filter */}
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full md:w-[180px] bg-slate-700/50 border-slate-600 text-slate-200">
                <SelectValue placeholder="筛选状态" />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="Available">可用</SelectItem>
                <SelectItem value="Charging">充电中</SelectItem>
                <SelectItem value="Offline">离线</SelectItem>
                <SelectItem value="Faulted">故障</SelectItem>
              </SelectContent>
            </Select>

            {/* View Mode Toggle */}
            <div className="flex gap-2">
              <Button
                variant={viewMode === 'grid' ? 'default' : 'outline'}
                size="icon"
                onClick={() => setViewMode('grid')}
                className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
              >
                <Grid3x3 className="h-4 w-4" />
              </Button>
              <Button
                variant={viewMode === 'list' ? 'default' : 'outline'}
                size="icon"
                onClick={() => setViewMode('list')}
                className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
              >
                <List className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Results Count */}
          <div className="mt-4 text-sm text-slate-400">
            共找到 {filteredChargers?.length || 0} 个充电桩
          </div>
        </CardContent>
      </Card>

      {/* Chargers List/Grid */}
      {filteredChargers && filteredChargers.length > 0 ? (
        viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredChargers.map((charger) => (
              <Card
                key={charger.id}
                className="bg-slate-800/80 backdrop-blur-sm border-slate-700 hover:border-purple-500/50 transition-colors cursor-pointer"
                onClick={() => router.push(`/chargers/${charger.id}`)}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-gradient-to-br from-purple-600/20 to-blue-600/20 rounded-lg">
                        <Zap className="h-5 w-5 text-purple-400" />
                      </div>
                      <div>
                        <CardTitle className="text-white text-lg">{charger.id}</CardTitle>
                        <p className="text-sm text-slate-400 mt-1">
                          {charger.vendor || 'Unknown'} {charger.model || ''}
                        </p>
                      </div>
                    </div>
                    <span
                      className={`px-2 py-1 rounded-md text-xs font-medium border ${getStatusColor(charger.status)}`}
                    >
                      {charger.status}
                    </span>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    {charger.location?.address && (
                      <div className="text-slate-400">
                        <span className="text-slate-500">位置：</span>
                        {charger.location.address}
                      </div>
                    )}
                    {charger.price_per_kwh && (
                      <div className="text-slate-400">
                        <span className="text-slate-500">价格：</span>
                        ¥{Number(charger.price_per_kwh).toFixed(2)}/kWh
                      </div>
                    )}
                    {charger.last_seen && (
                      <div className="text-slate-400">
                        <span className="text-slate-500">最后在线：</span>
                        {new Date(charger.last_seen).toLocaleString('zh-CN')}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 mt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/chargers/${charger.id}`);
                      }}
                      className="flex-1 bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                    >
                      <Eye className="h-4 w-4 mr-2" />
                      查看详情
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        // TODO: 实现远程控制
                      }}
                      className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                    >
                      <Power className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardContent className="pt-6">
              <div className="space-y-4">
                {filteredChargers.map((charger) => (
                  <div
                    key={charger.id}
                    className="flex items-center justify-between p-4 rounded-lg bg-slate-700/30 hover:bg-slate-700/50 transition-colors cursor-pointer"
                    onClick={() => router.push(`/chargers/${charger.id}`)}
                  >
                    <div className="flex items-center gap-4 flex-1">
                      <div className="p-2 bg-gradient-to-br from-purple-600/20 to-blue-600/20 rounded-lg">
                        <Zap className="h-5 w-5 text-purple-400" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <h3 className="text-white font-medium">{charger.id}</h3>
                          <span
                            className={`px-2 py-1 rounded-md text-xs font-medium border ${getStatusColor(charger.status)}`}
                          >
                            {charger.status}
                          </span>
                        </div>
                        <p className="text-sm text-slate-400 mt-1">
                          {charger.vendor || 'Unknown'} {charger.model || ''}
                          {charger.location?.address && ` · ${charger.location.address}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          router.push(`/chargers/${charger.id}`);
                        }}
                        className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        详情
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )
      ) : (
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardContent className="pt-12 pb-12 text-center">
            <Zap className="h-12 w-12 text-slate-500 mx-auto mb-4" />
            <p className="text-slate-400">没有找到充电桩</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}