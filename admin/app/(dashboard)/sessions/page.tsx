'use client';

import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Zap, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS, ACTIVE_SESSION_REFRESH_INTERVAL } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';

interface ActiveSession {
  id: number;
  transaction_id: number;
  charge_point_id: string;
  user_id?: string;
  start_time?: string;
  energy_kwh?: number;
  power_kw?: number;
  duration_minutes?: number;
  status: string;
}

export default function ActiveSessionsPage() {
  const { t } = useI18n();
  const { data: sessions, mutate, isLoading } = useSWR<ActiveSession[]>(
    `${API_ENDPOINTS.TRANSACTIONS}/active`,
    (url: string) => apiGet<ActiveSession[]>(url),
    { refreshInterval: ACTIVE_SESSION_REFRESH_INTERVAL }
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('活跃会话')}</h1>
          <p className="text-slate-400 mt-1">{t('实时监控进行中的充电会话（5 秒刷新）')}</p>
        </div>
        <Button variant="outline" className="border-slate-600" onClick={() => mutate()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          {t('刷新')}
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Zap className="h-5 w-5 text-yellow-400" />
            {t('进行中')} ({sessions?.length ?? 0})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-slate-400 text-center py-8">{t('加载中...')}</p>
          ) : !sessions?.length ? (
            <p className="text-slate-400 text-center py-12">{t('当前无进行中的充电会话')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    <th className="text-left py-2 px-2">{t('OCPP 交易号')}</th>
                    <th className="text-left py-2 px-2">{t('OCPP 身份')}</th>
                    <th className="text-left py-2 px-2">{t('已充电量')}</th>
                    <th className="text-left py-2 px-2">{t('功率')}</th>
                    <th className="text-left py-2 px-2">{t('时长(分)')}</th>
                    <th className="text-left py-2 px-2">{t('状态')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.id} className="border-b border-slate-700/50">
                      <td className="py-2 px-2">{s.transaction_id}</td>
                      <td className="py-2 px-2 font-mono text-xs">{s.charge_point_id}</td>
                      <td className="py-2 px-2">{s.energy_kwh?.toFixed(2) ?? '—'} kWh</td>
                      <td className="py-2 px-2">{s.power_kw?.toFixed(1) ?? '—'} kW</td>
                      <td className="py-2 px-2">{s.duration_minutes?.toFixed(0) ?? '—'}</td>
                      <td className="py-2 px-2">
                        <Badge className="bg-green-600">{s.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
