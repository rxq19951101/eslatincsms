'use client';

import { useRouter, useParams } from 'next/navigation';
import useSWR from 'swr';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { ChargePointDetail } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, Zap, Power, RotateCcw, Settings, Unlock, Play, Square, QrCode, Download, RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { API_BASE_URL } from '@/lib/constants';
import { useState } from 'react';

const fetcher = (url: string) => apiGet<ChargePointDetail>(url);

export default function ChargerDetailPage() {
  const router = useRouter();
  const params = useParams();
  const chargerId = params?.id as string;

  const { data: charger, error, isLoading, mutate } = useSWR<ChargePointDetail>(
    API_ENDPOINTS.CHARGER_DETAIL(chargerId),
    fetcher,
    {
      refreshInterval: 30000, // 30 秒自动刷新
    }
  );

  // 获取二维码列表
  const { data: qrData, mutate: mutateQr } = useSWR<{ qr_codes: Array<{ connector_id: number; qr_url: string; filename: string; exists: boolean }> }>(
    chargerId ? `${API_BASE_URL}/api/v1/chargers/${chargerId}/qr` : null,
    (url: string) => apiGet<{ qr_codes: Array<{ connector_id: number; qr_url: string; filename: string; exists: boolean }> }>(url)
  );

  const [generating, setGenerating] = useState<string | null>(null); // connector_id or 'all'

  const handleGenerateQr = async (connectorId?: number) => {
    if (!chargerId) return;
    
    const isAll = connectorId === undefined;
    setGenerating(isAll ? 'all' : String(connectorId));
    
    try {
      if (isAll) {
        // 生成所有connector的二维码
        await apiPost(`${API_BASE_URL}/api/v1/chargers/${chargerId}/qr/generate-all`, {});
        alert('所有二维码生成成功');
      } else {
        // 生成单个connector的二维码
        await apiPost(`${API_BASE_URL}/api/v1/chargers/${chargerId}/qr/${connectorId}/generate`, {});
        alert(`Connector ${connectorId} 的二维码生成成功`);
      }
      // 刷新二维码列表
      mutateQr();
    } catch (error) {
      console.error('生成二维码失败:', error);
      alert(isAll ? '生成二维码失败' : `Connector ${connectorId} 的二维码生成失败`);
    } finally {
      setGenerating(null);
    }
  };

  const handleRemoteStart = async () => {
    try {
      await apiPost(API_ENDPOINTS.OCPP_REMOTE_START, {
        charge_point_id: chargerId,
        id_tag: 'admin',
      });
      alert('远程启动充电请求已发送');
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Remote start failed:', error);
      alert('远程启动充电失败');
    }
  };

  const handleRemoteStop = async () => {
    try {
      await apiPost(API_ENDPOINTS.OCPP_REMOTE_STOP, {
        transaction_id: charger?.evses?.[0]?.evse_id, // 简化处理
      });
      alert('远程停止充电请求已发送');
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Remote stop failed:', error);
      alert('远程停止充电失败');
    }
  };

  const handleReset = async () => {
    if (!confirm('确定要重置充电桩吗？')) return;
    try {
      await apiPost(API_ENDPOINTS.OCPP_RESET, {
        charge_point_id: chargerId,
        type: 'Hard',
      });
      alert('重置请求已发送');
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Reset failed:', error);
      alert('重置失败');
    }
  };

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

  if (error || !charger) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">加载失败，充电桩不存在或已被删除</div>
        <Button onClick={() => router.back()} className="ml-4">
          返回
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.back()}
            className="bg-slate-800/50 border-slate-700 text-slate-300 hover:bg-slate-700"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold text-white">{charger.id}</h1>
              <Badge className={getStatusColor(charger.status)}>{charger.status}</Badge>
            </div>
            <p className="text-slate-400 mt-1">
              {charger.vendor || 'Unknown'} {charger.model || ''}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="basic" className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="basic" className="data-[state=active]:bg-slate-700">
            基本信息
          </TabsTrigger>
          <TabsTrigger value="status" className="data-[state=active]:bg-slate-700">
            状态监控
          </TabsTrigger>
          <TabsTrigger value="history" className="data-[state=active]:bg-slate-700">
            历史记录
          </TabsTrigger>
          <TabsTrigger value="control" className="data-[state=active]:bg-slate-700">
            远程控制
          </TabsTrigger>
        </TabsList>

        {/* Basic Info */}
        <TabsContent value="basic">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">基本信息</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-slate-400">充电桩 ID</label>
                  <p className="text-white mt-1">{charger.id}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">厂商</label>
                  <p className="text-white mt-1">{charger.vendor || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">型号</label>
                  <p className="text-white mt-1">{charger.model || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">序列号</label>
                  <p className="text-white mt-1">{charger.serial_number || 'N/A'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">固件版本</label>
                  <p className="text-white mt-1">{charger.firmware_version || 'N/A'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">连接器类型</label>
                  <p className="text-white mt-1">{charger.connector_type || 'Type2'}</p>
                </div>
              </div>
              {charger.location && (
                <div>
                  <label className="text-sm text-slate-400">位置</label>
                  <p className="text-white mt-1">
                    {charger.location.address || 'N/A'}
                    {charger.location.latitude && charger.location.longitude && (
                      <span className="text-slate-400 ml-2">
                        ({charger.location.latitude}, {charger.location.longitude})
                      </span>
                    )}
                  </p>
                </div>
              )}
              {charger.price_per_kwh && (
                <div>
                  <label className="text-sm text-slate-400">定价</label>
                  <p className="text-white mt-1">¥{Number(charger.price_per_kwh).toFixed(2)}/kWh</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* QR Codes */}
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-white flex items-center gap-2">
                  <QrCode className="h-5 w-5" />
                  二维码
                </CardTitle>
                {qrData && qrData.qr_codes && qrData.qr_codes.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleGenerateQr()}
                    disabled={generating === 'all'}
                    className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                  >
                    <RefreshCw className={`h-4 w-4 mr-2 ${generating === 'all' ? 'animate-spin' : ''}`} />
                    {generating === 'all' ? '生成中...' : '生成所有二维码'}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-slate-400 mb-4">
                每个connector对应一个二维码，用户扫码后可启动充电
              </div>
              {qrData && qrData.qr_codes && qrData.qr_codes.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {qrData.qr_codes.map((qr) => (
                    <div
                      key={qr.connector_id}
                      className="p-4 rounded-lg bg-slate-700/30 border border-slate-600"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm text-slate-400">Connector {qr.connector_id}</div>
                        {!qr.exists && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleGenerateQr(qr.connector_id)}
                            disabled={generating === String(qr.connector_id)}
                            className="bg-purple-600/50 border-purple-500 text-white hover:bg-purple-600 h-7 text-xs"
                          >
                            {generating === String(qr.connector_id) ? (
                              <>
                                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                                生成中
                              </>
                            ) : (
                              <>
                                <QrCode className="h-3 w-3 mr-1" />
                                生成
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                      {qr.exists ? (
                        <div className="space-y-2">
                          <div className="relative w-full aspect-square bg-white rounded-lg p-2 flex items-center justify-center">
                            <img
                              src={`${API_BASE_URL}${qr.qr_url}`}
                              alt={`QR Code for Connector ${qr.connector_id}`}
                              className="w-full h-full object-contain"
                            />
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            className="w-full bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                            onClick={() => {
                              const link = document.createElement('a');
                              link.href = `${API_BASE_URL}${qr.qr_url}`;
                              link.download = qr.filename;
                              link.click();
                            }}
                          >
                            <Download className="h-4 w-4 mr-2" />
                            下载
                          </Button>
                        </div>
                      ) : (
                        <div className="text-sm text-slate-500 py-8 text-center">
                          二维码未生成
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="text-slate-400 mb-4">暂无connector信息</div>
                  {charger?.evses && charger.evses.length > 0 && (
                    <Button
                      onClick={() => handleGenerateQr()}
                      disabled={generating === 'all'}
                      className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                    >
                      <RefreshCw className={`h-4 w-4 mr-2 ${generating === 'all' ? 'animate-spin' : ''}`} />
                      {generating === 'all' ? '生成中...' : '生成所有二维码'}
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Status Monitor */}
        <TabsContent value="status">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">状态监控</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm text-slate-400">当前状态</label>
                <div className="mt-2">
                  <Badge className={getStatusColor(charger.status)}>{charger.status}</Badge>
                </div>
              </div>
              {charger.last_seen && (
                <div>
                  <label className="text-sm text-slate-400">最后在线时间</label>
                  <p className="text-white mt-1">{new Date(charger.last_seen).toLocaleString('zh-CN')}</p>
                </div>
              )}
              {charger.evses && charger.evses.length > 0 && (
                <div>
                  <label className="text-sm text-slate-400 mb-2 block">EVSE 列表</label>
                  <div className="space-y-2">
                    {charger.evses.map((evse) => (
                      <div
                        key={evse.evse_id}
                        className="p-3 rounded-lg bg-slate-700/30 border border-slate-600"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-white font-medium">EVSE {evse.evse_id}</p>
                            <p className="text-sm text-slate-400">
                              {evse.connector_type} · {evse.max_power_kw ? `${evse.max_power_kw}kW` : 'N/A'}
                            </p>
                          </div>
                          <Badge className={getStatusColor(evse.status)}>{evse.status}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* History */}
        <TabsContent value="history">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">历史记录</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-slate-400">历史记录功能待实现</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Remote Control */}
        <TabsContent value="control">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">远程控制</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Button
                  onClick={handleRemoteStart}
                  className="bg-gradient-to-r from-green-600 to-green-700 hover:from-green-700 hover:to-green-800"
                >
                  <Play className="h-4 w-4 mr-2" />
                  启动充电
                </Button>
                <Button
                  onClick={handleRemoteStop}
                  className="bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800"
                >
                  <Square className="h-4 w-4 mr-2" />
                  停止充电
                </Button>
                <Button
                  onClick={handleReset}
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  重置充电桩
                </Button>
                <Button
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <Unlock className="h-4 w-4 mr-2" />
                  解锁连接器
                </Button>
                <Button
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <Settings className="h-4 w-4 mr-2" />
                  配置管理
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}