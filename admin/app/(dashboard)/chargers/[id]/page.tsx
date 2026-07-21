'use client';

import { useRouter, useParams } from 'next/navigation';
import useSWR from 'swr';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { AcceptanceReport, ChargePointDetail, Transaction } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, RotateCcw, Settings, Unlock, Play, Square, QrCode, Download, RefreshCw, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { API_BASE_URL } from '@/lib/constants';
import { useRef, useState } from 'react';
import { useI18n } from '@/lib/i18n';
import { activeTransactionFor, remoteCommandConfig, remoteStartPayload, remoteStopPayload, resetPayload } from '@/lib/ocpp';
import { IdempotencyIntentStore, requestIntent } from '@/lib/idempotency';
import QrPayloadCopy from '@/components/chargers/QrPayloadCopy';
import { formatDateTime } from '@/lib/localization';

interface ChargerQrCode {
  connector_id: number;
  qr_token?: string | null;
  qr_url: string;
  filename: string;
  exists: boolean;
}

const fetcher = (url: string) => apiGet<ChargePointDetail>(url);

export default function ChargerDetailPage() {
  const { locale, t } = useI18n();
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
  const { data: activeSessions, mutate: mutateSessions } = useSWR<Transaction[]>(
    charger ? API_ENDPOINTS.TRANSACTIONS_ACTIVE : null,
    (url: string) => apiGet<Transaction[]>(url),
    { refreshInterval: 5000 }
  );
  const ocppIdentity = charger?.ocpp_identity || chargerId;
  const activeSession = activeTransactionFor(activeSessions, charger?.id);
  const remoteIntents = useRef(new IdempotencyIntentStore()).current;

  // 获取二维码列表
  const { data: qrData, mutate: mutateQr } = useSWR<{ qr_codes: ChargerQrCode[] }>(
    chargerId ? `${API_BASE_URL}/api/v1/chargers/${chargerId}/qr` : null,
    (url: string) => apiGet<{ qr_codes: ChargerQrCode[] }>(url)
  );

  const [generating, setGenerating] = useState<string | null>(null); // connector_id or 'all'
  const [acceptanceReport, setAcceptanceReport] = useState<AcceptanceReport | null>(null);
  const [commissioning, setCommissioning] = useState(false);
  const [rotatedCredential, setRotatedCredential] = useState<string | null>(null);

  const handleAcceptanceReport = async () => {
    setCommissioning(true);
    try {
      const report = await apiPost<AcceptanceReport>(API_ENDPOINTS.CHARGER_ACCEPTANCE_REPORT(chargerId), {});
      setAcceptanceReport(report);
      mutate();
    } finally {
      setCommissioning(false);
    }
  };

  const handleCommission = async () => {
    setCommissioning(true);
    try {
      await apiPost(API_ENDPOINTS.CHARGER_COMMISSION(chargerId), {});
      await mutate();
      alert(t('充电桩已正式投运'));
    } catch {
      alert(t('验收未通过，不能正式投运'));
    } finally {
      setCommissioning(false);
    }
  };

  const handleRotateCredential = async () => {
    if (!confirm(t('轮换密钥后，设备必须立即更新凭据才能重新连接。是否继续？'))) return;
    const result = await apiPost<{ secret: string }>(API_ENDPOINTS.CHARGER_ROTATE_CREDENTIALS(chargerId), {});
    setRotatedCredential(result.secret);
    mutate();
  };

  const handleGenerateQr = async (connectorId?: number) => {
    if (!chargerId) return;
    
    const isAll = connectorId === undefined;
    setGenerating(isAll ? 'all' : String(connectorId));
    
    try {
      if (isAll) {
        // 生成所有connector的二维码
        await apiPost(`${API_BASE_URL}/api/v1/chargers/${chargerId}/qr/generate-all`, {});
        alert(t('所有二维码生成成功'));
      } else {
        // 生成单个connector的二维码
        await apiPost(`${API_BASE_URL}/api/v1/chargers/${chargerId}/qr/${connectorId}/generate`, {});
        alert(`${t('连接器')} ${connectorId}: ${t('二维码生成成功')}`);
      }
      // 刷新二维码列表
      mutateQr();
    } catch (error) {
      console.error('生成二维码失败:', error);
      alert(isAll ? t('生成二维码失败') : `${t('连接器')} ${connectorId}: ${t('生成二维码失败')}`);
    } finally {
      setGenerating(null);
    }
  };

  const handleRemoteStart = async () => {
    const payload = remoteStartPayload(ocppIdentity, charger?.evses?.[0]?.evse_id ?? 1);
    const intent = requestIntent('ocpp-remote-start', payload);
    try {
      await apiPost(
        API_ENDPOINTS.OCPP_REMOTE_START,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      alert(t('远程启动充电请求已发送'));
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Remote start failed:', error);
      alert(t('远程启动充电失败'));
    }
  };

  const handleRemoteStop = async () => {
    if (!activeSession) {
      alert(t('没有可停止的活动会话'));
      return;
    }
    const payload = remoteStopPayload(ocppIdentity, activeSession.transaction_id);
    const intent = requestIntent('ocpp-remote-stop', payload);
    try {
      await apiPost(
        API_ENDPOINTS.OCPP_REMOTE_STOP,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      alert(t('远程停止充电请求已发送'));
      mutate();
      mutateSessions();
    } catch (error) {
      console.error('Remote stop failed:', error);
      alert(t('远程停止充电失败'));
    }
  };

  const handleReset = async () => {
    if (!confirm(t('确定要重置充电桩吗？'))) return;
    const payload = resetPayload(ocppIdentity, 'Hard');
    const intent = requestIntent('ocpp-reset', payload);
    try {
      await apiPost(
        API_ENDPOINTS.OCPP_RESET,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      alert(t('重置请求已发送'));
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Reset failed:', error);
      alert(t('重置失败'));
    }
  };

  const getStatusColor = (status: string | null | undefined) => {
    switch (status?.toLowerCase()) {
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
        <div className="text-slate-400">{t('加载中...')}</div>
      </div>
    );
  }

  if (error || !charger) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{t('加载失败，充电桩不存在或已被删除')}</div>
        <Button onClick={() => router.back()} className="ml-4">
          {t('返回')}
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
              <h1 className="text-3xl font-bold text-white">{ocppIdentity}</h1>
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
            {t('基本信息')}
          </TabsTrigger>
          <TabsTrigger value="status" className="data-[state=active]:bg-slate-700">
            {t('状态监控')}
          </TabsTrigger>
          <TabsTrigger value="history" className="data-[state=active]:bg-slate-700">
            {t('历史记录')}
          </TabsTrigger>
          <TabsTrigger data-testid="admin-charger-control-tab" value="control" className="data-[state=active]:bg-slate-700">
            {t('远程控制')}
          </TabsTrigger>
          <TabsTrigger value="commissioning" className="data-[state=active]:bg-slate-700">
            {t('调试与投运')}
          </TabsTrigger>
        </TabsList>

        {/* Basic Info */}
        <TabsContent value="basic">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('基本信息')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-slate-400">{t('OCPP 身份')}</label>
                  <p className="text-white mt-1">{ocppIdentity}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('厂商')}</label>
                  <p className="text-white mt-1">{charger.vendor || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('型号')}</label>
                  <p className="text-white mt-1">{charger.model || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('序列号')}</label>
                  <p className="text-white mt-1">{charger.serial_number || 'N/A'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('固件版本')}</label>
                  <p className="text-white mt-1">{charger.firmware_version || 'N/A'}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('连接器类型')}</label>
                  <p className="text-white mt-1">{charger.connector_type || 'Type2'}</p>
                </div>
              </div>
              {charger.location && (
                <div>
                  <label className="text-sm text-slate-400">{t('位置')}</label>
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
                  <label className="text-sm text-slate-400">{t('定价')}</label>
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
                  {t('二维码')}
                </CardTitle>
                {qrData && qrData.qr_codes && qrData.qr_codes.length > 0 && (
                  <Button
                    data-testid="admin-qr-generate-all"
                    variant="outline"
                    size="sm"
                    onClick={() => handleGenerateQr()}
                    disabled={generating === 'all'}
                    className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                  >
                    <RefreshCw className={`h-4 w-4 mr-2 ${generating === 'all' ? 'animate-spin' : ''}`} />
                    {generating === 'all' ? t('生成中...') : t('生成所有二维码')}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-slate-400 mb-4">
                {t('每个连接器对应一个二维码，用户扫码后可启动充电')}
              </div>
              {qrData && qrData.qr_codes && qrData.qr_codes.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {qrData.qr_codes.map((qr) => (
                    <div
                      key={qr.connector_id}
                      data-testid={`admin-qr-card-${qr.connector_id}`}
                      className="p-4 rounded-lg bg-slate-700/30 border border-slate-600"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm text-slate-400">Connector {qr.connector_id}</div>
                        {!qr.exists && (
                          <Button
                            data-testid={`admin-qr-generate-${qr.connector_id}`}
                            variant="outline"
                            size="sm"
                            onClick={() => handleGenerateQr(qr.connector_id)}
                            disabled={generating === String(qr.connector_id)}
                            className="bg-purple-600/50 border-purple-500 text-white hover:bg-purple-600 h-7 text-xs"
                          >
                            {generating === String(qr.connector_id) ? (
                              <>
                                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                                {t('生成中')}
                              </>
                            ) : (
                              <>
                                <QrCode className="h-3 w-3 mr-1" />
                                {t('生成')}
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                      {qr.exists ? (
                        <div className="space-y-2">
                          <div className="relative w-full aspect-square bg-white rounded-lg p-2 flex items-center justify-center">
                            {/* eslint-disable-next-line @next/next/no-img-element -- QR URL is a generated API asset and must remain directly downloadable. */}
                            <img
                              src={`${API_BASE_URL}${qr.qr_url}`}
                              alt={`QR Code for Connector ${qr.connector_id}`}
                              className="w-full h-full object-contain"
                              data-testid={`admin-qr-image-${qr.connector_id}`}
                            />
                          </div>
                          <QrPayloadCopy qrToken={qr.qr_token} connectorId={qr.connector_id} />
                          <Button
                            data-testid={`admin-qr-download-${qr.connector_id}`}
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
                            {t('下载')}
                          </Button>
                        </div>
                      ) : (
                        <div className="text-sm text-slate-500 py-8 text-center">
                          {t('二维码未生成')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="text-slate-400 mb-4">{t('暂无connector信息')}</div>
                  {charger?.evses && charger.evses.length > 0 && (
                    <Button
                      data-testid="admin-qr-generate-all"
                      onClick={() => handleGenerateQr()}
                      disabled={generating === 'all'}
                      className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                    >
                      <RefreshCw className={`h-4 w-4 mr-2 ${generating === 'all' ? 'animate-spin' : ''}`} />
                      {generating === 'all' ? t('生成中...') : t('生成所有二维码')}
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
              <CardTitle className="text-white">{t('状态监控')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm text-slate-400">{t('当前状态')}</label>
                <div className="mt-2">
                  <Badge className={getStatusColor(charger.status)}>{charger.status}</Badge>
                </div>
              </div>
              {charger.last_seen && (
                <div>
                  <label className="text-sm text-slate-400">{t('最后在线时间')}</label>
                  <p className="text-white mt-1">
                    {formatDateTime(charger.last_seen, locale, t('common.notAvailable'))}
                  </p>
                </div>
              )}
              {charger.evses && charger.evses.length > 0 && (
                <div>
                  <label className="text-sm text-slate-400 mb-2 block">{t('EVSE 列表')}</label>
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
              <CardTitle className="text-white">{t('历史记录')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-slate-400">{t('历史记录功能待实现')}</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="commissioning">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader><CardTitle className="text-white">{t('设备调试与正式投运')}</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center justify-between rounded-lg border border-slate-700 p-4">
                <div>
                  <p className="text-sm text-slate-400">{t('当前投运状态')}</p>
                  <p className="mt-1 text-lg font-semibold text-white">{t(charger.commissioning_status || 'draft')}</p>
                </div>
                <ShieldCheck className="h-7 w-7 text-cyan-400" />
              </div>
              <div className="flex flex-wrap gap-3">
                <Button type="button" variant="outline" onClick={handleAcceptanceReport} disabled={commissioning}>
                  {t('生成自动验收报告')}
                </Button>
                <Button type="button" onClick={handleCommission} disabled={commissioning || !(acceptanceReport || charger.acceptance_report)?.passed}>
                  {t('确认正式投运')}
                </Button>
                <Button type="button" variant="destructive" onClick={handleRotateCredential}>{t('轮换设备密钥')}</Button>
              </div>
              {rotatedCredential && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-amber-100">
                  <p className="font-semibold">{t('新密钥只显示这一次')}</p>
                  <code className="mt-2 block break-all">{rotatedCredential}</code>
                </div>
              )}
              {(acceptanceReport || charger.acceptance_report) && (
                <div className="space-y-2">
                  {Object.entries((acceptanceReport || charger.acceptance_report)!.checks).map(([name, passed]) => (
                    <div key={name} className="flex items-center justify-between border-b border-slate-700 py-2">
                      <span className="text-slate-300">{t(name)}</span>
                      <Badge className={passed ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}>
                        {passed ? t('通过') : t('未通过')}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Remote Control */}
        <TabsContent value="control">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('远程控制')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Button
                  data-testid="admin-remote-start"
                  onClick={handleRemoteStart}
                  className="bg-gradient-to-r from-green-600 to-green-700 hover:from-green-700 hover:to-green-800"
                >
                  <Play className="h-4 w-4 mr-2" />
                  {t('启动充电')}
                </Button>
                <Button
                  data-testid="admin-remote-stop"
                  onClick={handleRemoteStop}
                  disabled={!activeSession}
                  title={!activeSession ? t('没有可停止的活动会话') : undefined}
                  className="bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800"
                >
                  <Square className="h-4 w-4 mr-2" />
                  {t('停止充电')}
                </Button>
                <Button
                  data-testid="admin-remote-reset"
                  onClick={handleReset}
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  {t('重置充电桩')}
                </Button>
                <Button
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <Unlock className="h-4 w-4 mr-2" />
                  {t('解锁连接器')}
                </Button>
                <Button
                  variant="outline"
                  className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  <Settings className="h-4 w-4 mr-2" />
                  {t('配置管理')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
