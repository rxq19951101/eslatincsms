'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import useSWR from 'swr';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ExternalLink, RefreshCw, Square, Zap } from 'lucide-react';
import { hasPermission, usePermissions } from '@/hooks/usePermissions';
import { ApiRequestError, apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS, ACTIVE_SESSION_REFRESH_INTERVAL } from '@/lib/constants';
import { IdempotencyIntentStore, requestIntent } from '@/lib/idempotency';
import { useI18n } from '@/lib/i18n';
import { formatDateTime, formatMeasurement, getStatusBadgeClass, getStatusMessageKey } from '@/lib/localization';
import { remoteCommandConfig, remoteStopPayload } from '@/lib/ocpp';
import RemoteStopDialog from '@/components/chargers/RemoteStopDialog';
import type { ActiveSession } from '@/types';

interface RemoteStopResponse {
  success: boolean;
}

export default function ActiveSessionsPage() {
  const { locale, t } = useI18n();
  const { permissions } = usePermissions();
  const canControlChargers = hasPermission(permissions, 'chargers.control');
  const remoteIntents = useRef(new IdempotencyIntentStore()).current;
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<ActiveSession | null>(null);
  const { data: sessions, error, mutate, isLoading } = useSWR<ActiveSession[]>(
    API_ENDPOINTS.TRANSACTIONS_ACTIVE,
    (url: string) => apiGet<ActiveSession[]>(url),
    { refreshInterval: ACTIVE_SESSION_REFRESH_INTERVAL }
  );

  const handleRemoteStop = async (operationReason: string) => {
    if (!selectedSession) return false;
    const payload = remoteStopPayload(selectedSession.id, operationReason);
    const intent = requestIntent('ocpp-remote-stop', payload);
    setStoppingId(selectedSession.id);
    try {
      const result = await apiPost<RemoteStopResponse>(
        API_ENDPOINTS.OCPP_REMOTE_STOP,
        payload,
        remoteCommandConfig(remoteIntents.keyFor(intent))
      );
      if (result.success) {
        remoteIntents.markSucceeded(intent);
        window.alert(t('远程停止已被充电桩接受'));
        return true;
      } else {
        window.alert(t('远程停止被充电桩拒绝'));
        return false;
      }
    } catch (requestError) {
      window.alert(t(requestError instanceof ApiRequestError && requestError.status === 503
        ? '充电桩离线，无法远程停止'
        : '远程停止请求失败'));
      return false;
    } finally {
      void mutate();
      setStoppingId(null);
    }
  };

  return (
    <div data-testid="admin-sessions-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('活跃会话')}</h1>
          <p className="text-slate-400 mt-1">{t('实时监控进行中的充电会话（5 秒刷新）')}</p>
        </div>
        <Button data-testid="admin-sessions-refresh" variant="outline" className="border-slate-600" onClick={() => mutate()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          {t('刷新')}
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Zap className="h-5 w-5 text-yellow-400" />
            {t('status.ongoing')} ({sessions?.length ?? 0})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-slate-400 text-center py-8">{t('加载中...')}</p>
          ) : error ? (
            <p className="text-red-400 text-center py-8">{t('加载失败，请刷新页面重试')}</p>
          ) : !sessions?.length ? (
            <p className="text-slate-400 text-center py-12">{t('当前无进行中的充电会话')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table data-testid="admin-sessions-table" className="w-full text-sm text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    <th className="text-left py-2 px-2">{t('站点')}</th>
                    <th className="text-left py-2 px-2">{t('充电桩 / 枪口')}</th>
                    <th className="text-left py-2 px-2">{t('用户')}</th>
                    <th className="text-left py-2 px-2">{t('开始时间')}</th>
                    <th className="text-left py-2 px-2">{t('实时计量')}</th>
                    <th className="text-left py-2 px-2">{t('时长(分)')}</th>
                    <th className="text-left py-2 px-2">{t('预估费用')}</th>
                    <th className="text-left py-2 px-2">{t('最后计量时间')}</th>
                    <th className="text-left py-2 px-2">{t('状态')}</th>
                    <th className="text-left py-2 px-2">{t('操作')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((session) => {
                    const fallback = t('common.notAvailable');
                    const chargerName = session.charger?.display_name?.trim() || session.charger?.display_code?.trim() || fallback;
                    const connectorName = session.connector?.physical_reference?.trim()
                      || (session.connector?.connector_number != null
                        ? t(`充电枪 ${session.connector.connector_number}`)
                        : fallback);
                    return (
                      <tr key={session.id} data-testid="admin-session-row" className="border-b border-slate-700/50 align-top">
                        <td className="py-3 px-2">
                          <div className="font-medium text-slate-100">{session.site?.name || fallback}</div>
                          <div className="text-xs text-slate-500">{session.site?.address || fallback}</div>
                        </td>
                        <td className="py-3 px-2">
                          <div className="font-medium text-slate-100">{chargerName}</div>
                          {session.charger?.display_name && session.charger.display_code && (
                            <div className="text-xs text-slate-500">{session.charger.display_code}</div>
                          )}
                          <div>{connectorName}</div>
                        </td>
                        <td className="py-3 px-2">{session.user_reference || fallback}</td>
                        <td className="py-3 px-2">{formatDateTime(session.start_time, locale, fallback)}</td>
                        <td className="py-3 px-2 whitespace-nowrap">
                          <div>{formatMeasurement(session.energy_kwh, 2, 'kWh', fallback)}</div>
                          <div className="text-slate-400">{formatMeasurement(session.power_kw, 1, 'kW', fallback)}</div>
                        </td>
                        <td className="py-3 px-2">{formatMeasurement(session.duration_minutes, 0, '', fallback)}</td>
                        <td className="py-3 px-2 whitespace-nowrap">
                          {session.estimated_cost && session.currency
                            ? `${session.currency} ${session.estimated_cost}`
                            : t('暂不可用')}
                        </td>
                        <td className="py-3 px-2">{formatDateTime(session.last_meter_at, locale, fallback)}</td>
                        <td className="py-3 px-2">
                          <Badge className={getStatusBadgeClass(session.status)}>{t(getStatusMessageKey(session.status))}</Badge>
                        </td>
                        <td className="py-3 px-2">
                          <div className="flex flex-col gap-2 min-w-24">
                            {session.charger?.id && (
                              <Button asChild size="sm" variant="outline" className="border-slate-600">
                                <Link href={`/chargers/${session.charger.id}`}>
                                  <ExternalLink className="h-3.5 w-3.5 mr-1" />{t('查看充电桩')}
                                </Link>
                              </Button>
                            )}
                            {canControlChargers && (
                              <Button
                                data-testid="session-remote-stop"
                                size="sm"
                                disabled={stoppingId !== null}
                                onClick={() => setSelectedSession(session)}
                                className="bg-red-700 hover:bg-red-800"
                              >
                                <Square className="h-3.5 w-3.5 mr-1" />
                                {stoppingId === session.id ? t('停止中...') : t('远程停止')}
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <RemoteStopDialog
        open={selectedSession !== null}
        session={selectedSession ? {
          id: selectedSession.id,
          site: selectedSession.site?.name || t('common.notAvailable'),
          charger: selectedSession.charger?.display_name?.trim() || selectedSession.charger?.display_code?.trim() || t('common.notAvailable'),
          connector: selectedSession.connector?.physical_reference?.trim()
            || (selectedSession.connector?.connector_number != null
              ? t(`充电枪 ${selectedSession.connector.connector_number}`)
              : t('common.notAvailable')),
        } : null}
        submitting={stoppingId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedSession(null);
        }}
        onConfirm={handleRemoteStop}
      />
    </div>
  );
}
