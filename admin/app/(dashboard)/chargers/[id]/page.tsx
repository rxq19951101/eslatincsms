'use client';

import { useRouter, useParams } from 'next/navigation';
import useSWR from 'swr';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { AcceptanceReport, ActiveSession, ChargePointDetail, ChargingRecord, PaginatedResponse } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertTriangle, ArrowLeft, RotateCcw, Unlock, Play, Square, QrCode, Download, RefreshCw, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { API_BASE_URL } from '@/lib/constants';
import { useRef, useState } from 'react';
import { useI18n } from '@/lib/i18n';
import { remoteCommandConfig, remoteStartPayload, remoteStopPayload, resetPayload, unlockPayload } from '@/lib/ocpp';
import { IdempotencyIntentStore, requestIntent } from '@/lib/idempotency';
import QrPayloadCopy from '@/components/chargers/QrPayloadCopy';
import RemoteStopDialog from '@/components/chargers/RemoteStopDialog';
import MaintenanceCommandDialog, { MaintenanceCommand } from '@/components/chargers/MaintenanceCommandDialog';
import ChargingRecordsTable from '@/components/transactions/ChargingRecordsTable';
import { formatDateTime } from '@/lib/localization';
import { hasPermission, usePermissions } from '@/hooks/usePermissions';

interface ChargerQrCode {
  connector_id: number;
  qr_token?: string | null;
  qr_url: string;
  filename: string;
  exists: boolean;
}

interface AdminChargePointDetail extends ChargePointDetail {
  display_code?: string | null;
  display_name?: string | null;
  location_hint?: string | null;
  site_name?: string | null;
  site?: {
    id?: string;
    site_code?: string | null;
    name?: string | null;
    address?: string | null;
  } | null;
}

const fetcher = (url: string) => apiGet<AdminChargePointDetail>(url);

export default function ChargerDetailPage() {
  const { locale, t } = useI18n();
  const { permissions } = usePermissions();
  const canControlChargers = hasPermission(permissions, 'chargers.control');
  const router = useRouter();
  const params = useParams();
  const chargerId = params?.id as string;

  const { data: charger, error, isLoading, mutate } = useSWR<AdminChargePointDetail>(
    API_ENDPOINTS.CHARGER_DETAIL(chargerId),
    fetcher,
    {
      refreshInterval: 30000, // 30 秒自动刷新
    }
  );
  const { data: activeSessions, mutate: mutateSessions } = useSWR<ActiveSession[]>(
    charger && canControlChargers ? API_ENDPOINTS.TRANSACTIONS_ACTIVE : null,
    (url: string) => apiGet<ActiveSession[]>(url),
    { refreshInterval: 5000 }
  );
  const historyUrl = charger?.ocpp_identity
    ? `${API_ENDPOINTS.TRANSACTIONS}?charge_point_id=${encodeURIComponent(charger.ocpp_identity)}&limit=10&offset=0`
    : null;
  const {
    data: chargingHistory,
    error: chargingHistoryError,
    isLoading: chargingHistoryLoading,
  } = useSWR<PaginatedResponse<ChargingRecord>>(
    historyUrl,
    (url: string) => apiGet<PaginatedResponse<ChargingRecord>>(url),
    { refreshInterval: 60000 }
  );
  const ocppIdentity = charger?.ocpp_identity || '';
  const displayName = charger?.display_name?.trim() || '';
  const displayCode = charger?.display_code?.trim() || '';
  const publicTitle = displayName || displayCode || t('common.notAvailable');
  const siteName = charger?.site?.name?.trim() || charger?.site_name?.trim() || t('common.notAvailable');
  const location = charger?.location_hint?.trim()
    || charger?.location?.address?.trim()
    || charger?.site?.address?.trim()
    || t('common.notAvailable');
  const ongoingSessions = activeSessions?.filter(
    (session) => session.charger?.id === charger?.id && session.status?.toLowerCase() === 'ongoing'
  ) ?? [];
  const connectorLabel = (physicalReference: string | null | undefined, connectorNumber: number | null | undefined) =>
    physicalReference?.trim()
      || (connectorNumber != null ? t(`充电枪 ${connectorNumber}`) : t('common.notAvailable'));
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
  const [remoteStartEvseId, setRemoteStartEvseId] = useState<number | null>(null);
  const [remoteStartReason, setRemoteStartReason] = useState('');
  const [remoteStartSubmitting, setRemoteStartSubmitting] = useState(false);
  const [remoteStopSession, setRemoteStopSession] = useState<ActiveSession | null>(null);
  const [remoteStopSubmitting, setRemoteStopSubmitting] = useState(false);
  const [maintenanceCommand, setMaintenanceCommand] = useState<MaintenanceCommand | null>(null);
  const [maintenanceSubmitting, setMaintenanceSubmitting] = useState(false);
  const [remoteStartFeedback, setRemoteStartFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

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
    if (!canControlChargers || !ocppIdentity) return;
    const selectedEvse = charger?.evses?.find((evse) => evse.evse_id === remoteStartEvseId);
    const operationReason = remoteStartReason.trim();
    if (!selectedEvse || selectedEvse.status?.toLowerCase() !== 'available') {
      setRemoteStartFeedback({ type: 'error', message: t('请选择状态为 Available 的枪口') });
      return;
    }
    if (operationReason.length < 3 || operationReason.length > 200) {
      setRemoteStartFeedback({ type: 'error', message: t('操作原因去除首尾空格后须为 3-200 个字符') });
      return;
    }

    const payload = remoteStartPayload(ocppIdentity, selectedEvse.evse_id, operationReason);
    const intent = requestIntent('ocpp-remote-start', payload);
    setRemoteStartSubmitting(true);
    setRemoteStartFeedback(null);
    try {
      await apiPost(
        API_ENDPOINTS.OCPP_REMOTE_START,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      setRemoteStartFeedback({ type: 'success', message: t('远程启动充电请求已发送') });
      mutate(); // 刷新数据
    } catch (error) {
      console.error('Remote start failed:', error);
      setRemoteStartFeedback({ type: 'error', message: t('远程启动充电失败') });
    } finally {
      setRemoteStartSubmitting(false);
    }
  };

  const handleRemoteStop = async (operationReason: string) => {
    if (!canControlChargers || !remoteStopSession) return false;
    const payload = remoteStopPayload(remoteStopSession.id, operationReason);
    const intent = requestIntent('ocpp-remote-stop', payload);
    setRemoteStopSubmitting(true);
    try {
      await apiPost(
        API_ENDPOINTS.OCPP_REMOTE_STOP,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      alert(t('远程停止充电请求已发送'));
      void mutate();
      void mutateSessions();
      return true;
    } catch (error) {
      console.error('Remote stop failed:', error);
      alert(t('远程停止充电失败'));
      return false;
    } finally {
      setRemoteStopSubmitting(false);
    }
  };

  const handleMaintenanceCommand = async (
    command: MaintenanceCommand,
    operationReason: string,
    connectorId?: number
  ) => {
    if (!canControlChargers || !ocppIdentity) return false;
    if (command === 'unlock' && connectorId === undefined) return false;

    const payload = command === 'unlock'
      ? unlockPayload(ocppIdentity, connectorId!, operationReason)
      : resetPayload(ocppIdentity, command === 'hard-reset' ? 'Hard' : 'Soft', operationReason);
    const intent = requestIntent(command === 'unlock' ? 'ocpp-unlock' : 'ocpp-reset', payload);
    setMaintenanceSubmitting(true);
    try {
      await apiPost(
        command === 'unlock' ? API_ENDPOINTS.OCPP_UNLOCK : API_ENDPOINTS.OCPP_RESET,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      remoteIntents.markSucceeded(intent);
      alert(t(command === 'unlock' ? '解锁请求已发送' : '重置请求已发送'));
      mutate(); // 刷新数据
      return true;
    } catch (error) {
      console.error('Maintenance command failed:', error);
      alert(t(command === 'unlock' ? '解锁失败' : '重置失败'));
      return false;
    } finally {
      setMaintenanceSubmitting(false);
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
              <h1 className="text-3xl font-bold text-white">{publicTitle}</h1>
              <Badge className={getStatusColor(charger.status)}>{charger.status}</Badge>
            </div>
            <p className="mt-1 text-slate-400">
              {displayName && displayCode ? `${displayCode} · ` : ''}
              {[charger.vendor, charger.model].filter(Boolean).join(' ') || t('common.notAvailable')}
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
          {canControlChargers && (
            <TabsTrigger data-testid="admin-charger-control-tab" value="control" className="data-[state=active]:bg-slate-700">
              {t('远程控制')}
            </TabsTrigger>
          )}
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
                  <label className="text-sm text-slate-400">{t('名称')}</label>
                  <p className="text-white mt-1">{publicTitle}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('公开编号')}</label>
                  <p className="text-white mt-1">{displayCode || t('common.notAvailable')}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('站点名称')}</label>
                  <p className="text-white mt-1">{siteName}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('位置')}</label>
                  <p className="text-white mt-1">
                    {location}
                    {charger.location?.latitude != null && charger.location?.longitude != null && (
                      <span className="ml-2 text-slate-400">
                        ({charger.location.latitude}, {charger.location.longitude})
                      </span>
                    )}
                  </p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('厂商')}</label>
                  <p className="text-white mt-1">{charger.vendor || t('common.notAvailable')}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('型号')}</label>
                  <p className="text-white mt-1">{charger.model || t('common.notAvailable')}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('序列号')}</label>
                  <p className="text-white mt-1">{charger.serial_number || t('common.notAvailable')}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('固件版本')}</label>
                  <p className="text-white mt-1">{charger.firmware_version || t('common.notAvailable')}</p>
                </div>
                <div>
                  <label className="text-sm text-slate-400">{t('连接器类型')}</label>
                  <p className="text-white mt-1">{charger.connector_type || t('common.notAvailable')}</p>
                </div>
              </div>
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
                        <div className="text-sm text-slate-400">
                          {connectorLabel(
                            charger.evses?.find((evse) => evse.evse_id === qr.connector_id)?.physical_reference,
                            qr.connector_id
                          )}
                        </div>
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
                              alt={`${t('二维码')} - ${connectorLabel(
                                charger.evses?.find((evse) => evse.evse_id === qr.connector_id)?.physical_reference,
                                qr.connector_id
                              )}`}
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
                            <p className="text-white font-medium">
                              {connectorLabel(evse.physical_reference, evse.evse_id)}
                            </p>
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
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <div>
                <CardTitle className="text-white">{t('transactions.recent')}</CardTitle>
                <p className="mt-1 text-sm text-slate-400">{t('transactions.recentDescription')}</p>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push(`/transactions?charge_point_id=${encodeURIComponent(charger.ocpp_identity)}`)}
              >
                {t('transactions.viewAll')}
              </Button>
            </CardHeader>
            <CardContent>
              {chargingHistoryLoading && !chargingHistory ? (
                <p className="py-10 text-center text-slate-400">{t('transactions.loading')}</p>
              ) : chargingHistoryError ? (
                <p role="alert" className="py-10 text-center text-red-400">{t('transactions.loadFailed')}</p>
              ) : (
                <ChargingRecordsTable
                  records={Array.isArray(chargingHistory?.items) ? chargingHistory.items : []}
                  compact
                  showSite={false}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="commissioning">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader><CardTitle className="text-white">{t('设备调试与正式投运')}</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div
                data-testid="admin-charger-technical-identity"
                className="rounded-lg border border-slate-700 bg-slate-900/30 p-4"
              >
                <p className="text-sm text-slate-400">{t('OCPP 技术身份')}</p>
                <code className="mt-1 block break-all text-slate-100">
                  {ocppIdentity || t('common.notAvailable')}
                </code>
              </div>
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
        {canControlChargers && <TabsContent value="control">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('远程控制')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-900/30 p-4">
                <div>
                  <h3 className="flex items-center gap-2 font-semibold text-white">
                    <Play className="h-4 w-4 text-green-400" />
                    {t('远程启动充电')}
                  </h3>
                  <p className="mt-1 text-sm text-slate-400">{t('请选择一个可用枪口并填写操作原因')}</p>
                </div>

                <fieldset className="space-y-2" disabled={remoteStartSubmitting}>
                  <legend className="text-sm font-medium text-slate-300">{t('选择枪口')}</legend>
                  {charger.evses && charger.evses.length > 0 ? (
                    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                      {charger.evses.map((evse) => {
                        const isAvailable = evse.status?.toLowerCase() === 'available';
                        return (
                          <label
                            key={evse.evse_id}
                            className={`rounded-md border p-3 ${
                              isAvailable
                                ? 'cursor-pointer border-slate-600 bg-slate-800/70 hover:border-green-500/70'
                                : 'cursor-not-allowed border-slate-700 bg-slate-800/30 opacity-60'
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <input
                                type="radio"
                                name="remote-start-evse"
                                value={evse.evse_id}
                                checked={remoteStartEvseId === evse.evse_id}
                                onChange={() => {
                                  setRemoteStartEvseId(evse.evse_id);
                                  setRemoteStartFeedback(null);
                                }}
                                disabled={!isAvailable || remoteStartSubmitting}
                                className="mt-1 h-4 w-4 accent-green-600"
                                data-testid={`admin-remote-start-evse-${evse.evse_id}`}
                              />
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-medium text-white">
                                    {connectorLabel(evse.physical_reference, evse.evse_id)}
                                  </span>
                                  <Badge className={getStatusColor(evse.status)}>{t(evse.status)}</Badge>
                                </div>
                                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                                  <div>
                                    <dt className="text-slate-500">{t('物理编号')}</dt>
                                    <dd className="text-slate-300">{evse.physical_reference || t('common.notAvailable')}</dd>
                                  </div>
                                  <div>
                                    <dt className="text-slate-500">{t('连接器类型')}</dt>
                                    <dd className="text-slate-300">{evse.connector_type || t('common.notAvailable')}</dd>
                                  </div>
                                  <div>
                                    <dt className="text-slate-500">{t('最大功率')}</dt>
                                    <dd className="text-slate-300">
                                      {evse.max_power_kw != null ? `${evse.max_power_kw} kW` : t('common.notAvailable')}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt className="text-slate-500">{t('状态')}</dt>
                                    <dd className="text-slate-300">{t(evse.status)}</dd>
                                  </div>
                                </dl>
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="rounded-md border border-slate-700 p-3 text-sm text-slate-400">
                      {t('暂无connector信息')}
                    </p>
                  )}
                </fieldset>

                <div>
                  <label htmlFor="remote-start-reason" className="text-sm font-medium text-slate-300">
                    {t('操作原因')}
                  </label>
                  <textarea
                    id="remote-start-reason"
                    data-testid="admin-remote-start-reason"
                    value={remoteStartReason}
                    onChange={(event) => {
                      setRemoteStartReason(event.target.value);
                      setRemoteStartFeedback(null);
                    }}
                    disabled={remoteStartSubmitting}
                    maxLength={200}
                    rows={3}
                    placeholder={t('请填写现场调试或故障处置原因')}
                    className="mt-2 w-full resize-y rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500 disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <div className="mt-1 flex justify-between gap-3 text-xs">
                    <span className={remoteStartReason.trim().length > 0 && remoteStartReason.trim().length < 3 ? 'text-red-400' : 'text-slate-500'}>
                      {t('操作原因去除首尾空格后须为 3-200 个字符')}
                    </span>
                    <span className="shrink-0 text-slate-500">{remoteStartReason.trim().length}/200</span>
                  </div>
                </div>

                <Button
                  data-testid="admin-remote-start"
                  onClick={handleRemoteStart}
                  disabled={
                    remoteStartSubmitting ||
                    !charger.evses?.some(
                      (evse) => evse.evse_id === remoteStartEvseId && evse.status?.toLowerCase() === 'available'
                    ) ||
                    remoteStartReason.trim().length < 3 ||
                    remoteStartReason.trim().length > 200
                  }
                  className="w-full bg-gradient-to-r from-green-600 to-green-700 hover:from-green-700 hover:to-green-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {remoteStartSubmitting ? (
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  {remoteStartSubmitting ? t('远程启动请求提交中...') : t('启动充电')}
                </Button>

                {remoteStartSubmitting && (
                  <p role="status" className="text-sm text-cyan-300">{t('远程启动请求提交中，请勿重复操作')}</p>
                )}
                {!remoteStartSubmitting && remoteStartFeedback && (
                  <p
                    role={remoteStartFeedback.type === 'error' ? 'alert' : 'status'}
                    className={remoteStartFeedback.type === 'error' ? 'text-sm text-red-400' : 'text-sm text-green-400'}
                  >
                    {remoteStartFeedback.message}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-3 rounded-lg border border-slate-700 bg-slate-800/50 p-4 md:col-span-2">
                  <div>
                    <h3 className="font-medium text-slate-100">{t('选择要停止的会话')}</h3>
                    <p className="mt-1 text-sm text-slate-400">{t('远程停止必须绑定明确的进行中会话')}</p>
                  </div>
                  {ongoingSessions.length === 0 ? (
                    <p className="text-sm text-slate-400">{t('该充电桩当前没有进行中的会话')}</p>
                  ) : (
                    <div className="space-y-2">
                      {ongoingSessions.map((session) => (
                        <div
                          key={session.id}
                          className="flex flex-col gap-3 rounded-md border border-slate-700 bg-slate-900/70 p-3 sm:flex-row sm:items-center sm:justify-between"
                        >
                          <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
                            <dt className="text-slate-500">{t('枪口')}</dt>
                            <dd className="text-slate-200">
                              {connectorLabel(session.connector?.physical_reference, session.connector?.connector_number)}
                            </dd>
                            <dt className="text-slate-500">{t('开始时间')}</dt>
                            <dd className="text-slate-200">
                              {formatDateTime(session.start_time, locale, t('common.notAvailable'))}
                            </dd>
                          </dl>
                          <Button
                            data-testid="admin-remote-stop"
                            onClick={() => setRemoteStopSession(session)}
                            disabled={remoteStopSubmitting}
                            className="bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800"
                          >
                            <Square className="h-4 w-4 mr-2" />
                            {t('停止充电')}
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="space-y-3 rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4">
                  <div>
                    <h3 className="font-medium text-slate-100">{t('维护命令')}</h3>
                    <p className="mt-1 text-sm text-slate-400">{t('Soft Reset 是默认维护入口，通常不会中断进行中的充电。')}</p>
                  </div>
                  <Button
                    data-testid="admin-soft-reset"
                    onClick={() => setMaintenanceCommand('soft-reset')}
                    disabled={maintenanceSubmitting}
                    className="w-full bg-cyan-700 hover:bg-cyan-800"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    {t('Soft Reset')}
                  </Button>
                  <Button
                    data-testid="admin-unlock-connector"
                    onClick={() => setMaintenanceCommand('unlock')}
                    disabled={maintenanceSubmitting}
                    variant="outline"
                    className="w-full border-slate-600 bg-slate-700/50 text-slate-200 hover:bg-slate-600"
                  >
                    <Unlock className="mr-2 h-4 w-4" />
                    {t('解锁连接器')}
                  </Button>
                </div>

                <div className="space-y-3 rounded-lg border border-red-500/40 bg-red-500/5 p-4">
                  <div>
                    <h3 className="flex items-center gap-2 font-medium text-red-200">
                      <AlertTriangle className="h-4 w-4" />
                      {t('危险操作')}
                    </h3>
                    <p className="mt-1 text-sm text-red-200/70">{t('Hard Reset 会重启设备，并可能中断进行中的充电和现场通信。')}</p>
                  </div>
                  <Button
                    data-testid="admin-hard-reset"
                    onClick={() => setMaintenanceCommand('hard-reset')}
                    disabled={maintenanceSubmitting}
                    variant="destructive"
                    className="w-full"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    {t('Hard Reset')}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>}
      </Tabs>
      {canControlChargers && <RemoteStopDialog
        open={remoteStopSession !== null}
        session={remoteStopSession ? {
          id: remoteStopSession.id,
          site: remoteStopSession.site?.name || t('common.notAvailable'),
          charger: remoteStopSession.charger?.display_name?.trim()
            || remoteStopSession.charger?.display_code?.trim()
            || t('common.notAvailable'),
          connector: connectorLabel(
            remoteStopSession.connector?.physical_reference,
            remoteStopSession.connector?.connector_number
          ),
        } : null}
        submitting={remoteStopSubmitting}
        onOpenChange={(open) => {
          if (!open) setRemoteStopSession(null);
        }}
        onConfirm={handleRemoteStop}
      />}
      {canControlChargers && (
        <MaintenanceCommandDialog
          open={maintenanceCommand !== null}
          command={maintenanceCommand}
          evses={(charger.evses || []).map((evse) => ({
            id: evse.evse_id,
            label: connectorLabel(evse.physical_reference, evse.evse_id),
            status: evse.status,
          }))}
          submitting={maintenanceSubmitting}
          onOpenChange={(open) => {
            if (!open) setMaintenanceCommand(null);
          }}
          onConfirm={handleMaintenanceCommand}
        />
      )}
    </div>
  );
}
