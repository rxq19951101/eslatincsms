'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { apiGet, apiPut } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Alert } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/lib/i18n';

const fetcher = (url: string) => apiGet<Alert[]>(url);

export default function AlertsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const { t, locale } = useI18n();

  const { data: alerts, error, isLoading, mutate } = useSWR<Alert[]>(
    API_ENDPOINTS.ALERTS,
    fetcher,
    {
      refreshInterval: 30000,
    }
  );

  const filteredAlerts = alerts?.filter((alert) => {
    const matchesSearch =
      alert.ocpp_identity?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      alert.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesSeverity = severityFilter === 'all' || alert.severity === severityFilter;
    const matchesStatus = statusFilter === 'all' || alert.status === statusFilter;
    return matchesSearch && matchesSeverity && matchesStatus;
  });

  const handleAcknowledge = async (alertId: string) => {
    try {
      await apiPut(API_ENDPOINTS.ALERT_ACKNOWLEDGE(alertId));
      mutate();
      alert(t('告警已确认'));
    } catch (error) {
      console.error('Acknowledge failed:', error);
      alert(t('确认失败'));
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      await apiPut(API_ENDPOINTS.ALERT_RESOLVE(alertId));
      mutate();
      alert(t('告警已解决'));
    } catch (error) {
      console.error('Resolve failed:', error);
      alert(t('解决失败'));
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'warning':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
      case 'info':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/50';
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

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{t('加载失败，请刷新页面重试')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">{t('告警管理')}</h1>
        <p className="text-slate-400 mt-1">{t('查看和处理系统告警')}</p>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                type="text"
                placeholder={t('搜索 OCPP 身份、描述...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-slate-700/50 border-slate-600"
              />
            </div>
            <Select value={severityFilter} onValueChange={setSeverityFilter}>
              <SelectTrigger className="w-full md:w-[180px] bg-slate-700/50 border-slate-600">
                <SelectValue placeholder={t('严重程度')} />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">{t('全部')}</SelectItem>
                <SelectItem value="critical">{t('严重')}</SelectItem>
                <SelectItem value="warning">{t('警告')}</SelectItem>
                <SelectItem value="info">{t('信息')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full md:w-[180px] bg-slate-700/50 border-slate-600">
                <SelectValue placeholder={t('状态')} />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">{t('全部')}</SelectItem>
                <SelectItem value="pending">{t('待处理')}</SelectItem>
                <SelectItem value="acknowledged">{t('已确认')}</SelectItem>
                <SelectItem value="resolved">{t('已解决')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredAlerts && filteredAlerts.length > 0 ? (
          filteredAlerts.map((alert) => (
            <Card
              key={alert.id}
              className="bg-slate-800/80 backdrop-blur-sm border-slate-700 hover:border-purple-500/50 transition-colors"
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className={`h-5 w-5 ${
                      alert.severity === 'critical' ? 'text-red-400' :
                      alert.severity === 'warning' ? 'text-yellow-400' : 'text-blue-400'
                    }`} />
                    <div>
                      <CardTitle className="text-white text-lg">{t(alert.title)}</CardTitle>
                      <Badge className={`mt-2 ${getSeverityColor(alert.severity)}`}>
                        {t(alert.severity)}
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-slate-400">{t('描述')}</p>
                  <p className="text-white mt-1">{t(alert.description)}</p>
                </div>
                {alert.ocpp_identity && (
                  <div>
                    <p className="text-sm text-slate-400">{t('OCPP 身份')}</p>
                    <p className="text-white mt-1">{alert.ocpp_identity}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-slate-400">{t('发生时间')}</p>
                  <p className="text-white mt-1">
                    {new Date(alert.created_at).toLocaleString(
                      locale === 'en' ? 'en-US' : locale === 'es' ? 'es-ES' : 'zh-CN'
                    )}
                  </p>
                </div>
                <div className="flex gap-2 pt-2">
                  {alert.status === 'pending' && (
                    <>
                      <Button
                        size="sm"
                        onClick={() => handleAcknowledge(alert.id)}
                        className="flex-1 bg-yellow-600 hover:bg-yellow-700"
                      >
                        <CheckCircle className="h-4 w-4 mr-2" />
                        {t('确认')}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleResolve(alert.id)}
                        className="flex-1 bg-green-600 hover:bg-green-700"
                      >
                        <XCircle className="h-4 w-4 mr-2" />
                        {t('解决')}
                      </Button>
                    </>
                  )}
                  {alert.status === 'acknowledged' && (
                    <Button
                      size="sm"
                      onClick={() => handleResolve(alert.id)}
                      className="flex-1 bg-green-600 hover:bg-green-700"
                    >
                      <XCircle className="h-4 w-4 mr-2" />
                      {t('解决')}
                    </Button>
                  )}
                  {alert.status === 'resolved' && (
                      <div className="flex-1 text-center text-sm text-slate-400">
                      {t('已解决')}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="col-span-full text-center py-12">
            <AlertTriangle className="h-12 w-12 text-slate-500 mx-auto mb-4" />
            <p className="text-slate-400">{t('没有找到告警')}</p>
          </div>
        )}
      </div>

      <AlertRulesSection />
    </div>
  );
}

interface AlertRule {
  id: string;
  name: string;
  alert_type: string;
  severity: string;
  is_enabled: boolean;
}

function AlertRulesSection() {
  const { t } = useI18n();
  const { data: rules, isLoading } = useSWR<AlertRule[]>(
    API_ENDPOINTS.ALERT_RULES,
    (url: string) => apiGet<AlertRule[]>(url)
  );

  return (
    <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
      <CardHeader>
        <CardTitle className="text-white">{t('告警规则')}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-slate-400">{t('加载规则...')}</p>
        ) : !rules?.length ? (
          <p className="text-slate-400">{t('暂无告警规则，可通过 API 创建')}</p>
        ) : (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div key={rule.id} className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg">
                <div>
                  <p className="text-white font-medium">{t(rule.name)}</p>
                  <p className="text-slate-400 text-sm">{t(rule.alert_type)} · {t(rule.severity)}</p>
                </div>
                <Badge variant={rule.is_enabled ? 'default' : 'secondary'}>
                  {rule.is_enabled ? t('启用') : t('禁用')}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
