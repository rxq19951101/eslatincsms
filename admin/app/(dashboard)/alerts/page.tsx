'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { apiGet, apiPut } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Alert } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, AlertTriangle, CheckCircle, XCircle, MapPin, Cpu, CircuitBoard } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/lib/i18n';
import { matchesSearchQuery } from '@/lib/search';
import { hasPermission, usePermissions } from '@/hooks/usePermissions';
import {
  alertDateLocale,
  alertRawMessage,
  alertSeverityLabel,
  alertStatusLabel,
  alertText,
  localizedAlertMessage,
  sanitizedAlertMessageParams,
} from './alert-i18n';

const fetcher = (url: string) => apiGet<Alert[]>(url);

export default function AlertsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const { locale } = useI18n();
  const { permissions } = usePermissions();
  const canWriteAlerts = hasPermission(permissions, 'alerts.write');

  const { data: alerts, error, isLoading, mutate } = useSWR<Alert[]>(
    API_ENDPOINTS.ALERTS,
    fetcher,
    {
      refreshInterval: 30000,
    }
  );

  const filteredAlerts = alerts?.filter((alert) => {
    const localizedMessage = localizedAlertMessage(locale, alert);
    const matchesSearch = matchesSearchQuery(searchQuery, [
      alert.alert_code,
      localizedMessage.title,
      localizedMessage.description,
      alert.site?.name,
      alert.site?.address,
      alert.charge_point?.ocpp_identity || alert.ocpp_identity,
      alert.charge_point?.model,
      alert.charge_point?.serial_number,
      alert.evse?.evse_id,
      alert.evse?.physical_reference,
    ]);
    const matchesSeverity = severityFilter === 'all' || alert.severity === severityFilter;
    const matchesStatus = statusFilter === 'all' || alert.status === statusFilter;
    return matchesSearch && matchesSeverity && matchesStatus;
  });

  const handleAcknowledge = async (alertId: string) => {
    try {
      await apiPut(API_ENDPOINTS.ALERT_ACKNOWLEDGE(alertId));
      mutate();
      window.alert(alertText(locale, 'acknowledgedNotice'));
    } catch (error) {
      console.error('Acknowledge failed:', error);
      window.alert(alertText(locale, 'acknowledgeFailed'));
    }
  };

  const handleResolve = async (alertId: string) => {
    try {
      await apiPut(API_ENDPOINTS.ALERT_RESOLVE(alertId));
      mutate();
      window.alert(alertText(locale, 'resolvedNotice'));
    } catch (error) {
      console.error('Resolve failed:', error);
      window.alert(alertText(locale, 'resolveFailed'));
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
        <div className="text-slate-400">{alertText(locale, 'loading')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{alertText(locale, 'loadFailed')}</div>
      </div>
    );
  }

  return (
    <div data-testid="admin-alerts-page" className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">{alertText(locale, 'pageTitle')}</h1>
        <p className="text-slate-400 mt-1">{alertText(locale, 'pageSubtitle')}</p>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                data-testid="admin-alert-search"
                type="text"
                placeholder={alertText(locale, 'searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-slate-700/50 border-slate-600"
              />
            </div>
            <Select value={severityFilter} onValueChange={setSeverityFilter}>
              <SelectTrigger data-testid="admin-alert-severity-filter" className="w-full md:w-[180px] bg-slate-700/50 border-slate-600">
                <SelectValue placeholder={alertText(locale, 'severity')} />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">{alertText(locale, 'all')}</SelectItem>
                <SelectItem value="critical">{alertSeverityLabel(locale, 'critical')}</SelectItem>
                <SelectItem value="warning">{alertSeverityLabel(locale, 'warning')}</SelectItem>
                <SelectItem value="info">{alertSeverityLabel(locale, 'info')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger data-testid="admin-alert-status-filter" className="w-full md:w-[180px] bg-slate-700/50 border-slate-600">
                <SelectValue placeholder={alertText(locale, 'status')} />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">{alertText(locale, 'all')}</SelectItem>
                <SelectItem value="pending">{alertStatusLabel(locale, 'pending')}</SelectItem>
                <SelectItem value="acknowledged">{alertStatusLabel(locale, 'acknowledged')}</SelectItem>
                <SelectItem value="resolved">{alertStatusLabel(locale, 'resolved')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {filteredAlerts && filteredAlerts.length > 0 ? (
          filteredAlerts.map((alert) => {
            const message = localizedAlertMessage(locale, alert);
            const rawMessage = alertRawMessage(alert);
            const siteCode = alert.site?.site_code;
            const ocppIdentity = alert.charge_point?.ocpp_identity || alert.ocpp_identity;
            const safeMessageParams = sanitizedAlertMessageParams(alert.message_params);
            const hasMessageParams = Object.keys(safeMessageParams).length > 0;

            return (
              <Card
                key={alert.id}
                data-testid="admin-alert-card"
                className="bg-slate-800/80 backdrop-blur-sm border-slate-700 hover:border-purple-500/50 transition-colors"
              >
                <CardContent className="p-4 md:p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${
                          alert.severity === 'critical' ? 'text-red-400' :
                          alert.severity === 'warning' ? 'text-yellow-400' : 'text-blue-400'
                        }`} />
                        <div className="min-w-0">
                          <h2 className="text-base font-semibold text-white">{message.title}</h2>
                          <p className="mt-1 text-sm text-slate-300">{message.description}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 pl-8">
                        <Badge className={getSeverityColor(alert.severity)}>
                          {alertSeverityLabel(locale, alert.severity)}
                        </Badge>
                        <Badge variant="outline" className="border-slate-600 text-slate-200">
                          {alertStatusLabel(locale, alert.status)}
                        </Badge>
                        <span className="self-center text-xs text-slate-400">
                          {alertText(locale, 'occurredAt')}: {new Date(alert.created_at).toLocaleString(alertDateLocale(locale))}
                        </span>
                      </div>
                    </div>

                    <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
                      {canWriteAlerts && alert.status === 'pending' && (
                        <Button
                          data-testid="admin-alert-acknowledge"
                          size="sm"
                          onClick={() => handleAcknowledge(alert.id)}
                          className="bg-yellow-600 hover:bg-yellow-700"
                        >
                          <CheckCircle className="h-4 w-4" />
                          {alertText(locale, 'acknowledge')}
                        </Button>
                      )}
                      {canWriteAlerts && alert.status !== 'resolved' && (
                        <Button
                          data-testid="admin-alert-resolve"
                          size="sm"
                          onClick={() => handleResolve(alert.id)}
                          className="bg-green-600 hover:bg-green-700"
                        >
                          <XCircle className="h-4 w-4" />
                          {alertText(locale, 'resolve')}
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 rounded-lg border border-slate-700 bg-slate-900/35 p-3 md:grid-cols-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                        <MapPin className="h-3.5 w-3.5" /> {alertText(locale, 'site')}
                      </p>
                      <p className="mt-1 truncate text-sm font-medium text-white">{alert.site?.name || alertText(locale, 'unassigned')}</p>
                      {alert.site?.address && <p className="truncate text-xs text-slate-400">{alert.site.address}</p>}
                      {siteCode && (
                        <Button asChild variant="link" size="sm" className="h-auto p-0 text-purple-300">
                          <Link href={`/sites/${encodeURIComponent(siteCode)}`}>{alertText(locale, 'viewSite')}</Link>
                        </Button>
                      )}
                    </div>

                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                        <Cpu className="h-3.5 w-3.5" /> {alertText(locale, 'device')}
                      </p>
                      <p className="mt-1 truncate text-sm font-medium text-white">{ocppIdentity || alertText(locale, 'unassigned')}</p>
                      {(alert.charge_point?.model || alert.charge_point?.serial_number) && (
                        <p className="truncate text-xs text-slate-400">
                          {alert.charge_point?.model && `${alertText(locale, 'model')}: ${alert.charge_point.model}`}
                          {alert.charge_point?.model && alert.charge_point?.serial_number && ' · '}
                          {alert.charge_point?.serial_number && `${alertText(locale, 'serialNumber')}: ${alert.charge_point.serial_number}`}
                        </p>
                      )}
                      {ocppIdentity && (
                        <Button asChild variant="link" size="sm" className="h-auto p-0 text-purple-300">
                          <Link href={`/chargers/${encodeURIComponent(ocppIdentity)}`}>{alertText(locale, 'viewDevice')}</Link>
                        </Button>
                      )}
                    </div>

                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                        <CircuitBoard className="h-3.5 w-3.5" /> {alertText(locale, 'evse')}
                      </p>
                      <p className="mt-1 truncate text-sm font-medium text-white">
                        {alert.evse?.evse_id == null ? alertText(locale, 'unassigned') : `EVSE ${alert.evse.evse_id}`}
                      </p>
                      {alert.evse?.physical_reference && (
                        <p className="truncate text-xs text-slate-400">
                          {alertText(locale, 'physicalReference')}: {alert.evse.physical_reference}
                        </p>
                      )}
                    </div>
                  </div>

                  <details data-testid="admin-alert-technical-details" className="mt-3 text-sm text-slate-300">
                    <summary className="w-fit cursor-pointer select-none text-slate-400 hover:text-slate-200">
                      {alertText(locale, 'technicalDetails')}
                    </summary>
                    <div className="mt-2 space-y-2 rounded-md bg-slate-950/60 p-3 font-mono text-xs">
                      {alert.alert_code && <p><span className="text-slate-500">{alertText(locale, 'alertCode')}:</span> {alert.alert_code}</p>}
                      {rawMessage && <p className="whitespace-pre-wrap break-words"><span className="text-slate-500">{alertText(locale, 'rawMessage')}:</span> {rawMessage}</p>}
                      {hasMessageParams && (
                        <div>
                          <p className="text-slate-500">{alertText(locale, 'messageParams')}:</p>
                          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words">{JSON.stringify(safeMessageParams, null, 2)}</pre>
                        </div>
                      )}
                      {!alert.alert_code && !rawMessage && !hasMessageParams && <p>{alertText(locale, 'noTechnicalDetails')}</p>}
                    </div>
                  </details>
                </CardContent>
              </Card>
            );
          })
        ) : (
          <div className="text-center py-12">
            <AlertTriangle className="h-12 w-12 text-slate-500 mx-auto mb-4" />
            <p className="text-slate-400">{alertText(locale, 'empty')}</p>
          </div>
        )}
      </div>

      <AlertRulesSection permissions={permissions} />
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

function AlertRulesSection({ permissions }: { permissions: string[] }) {
  const { t } = useI18n();
  const canReadRules = hasPermission(permissions, 'alert_rules.read');
  const { data: rules, isLoading } = useSWR<AlertRule[]>(
    canReadRules ? API_ENDPOINTS.ALERT_RULES : null,
    (url: string) => apiGet<AlertRule[]>(url)
  );

  if (!canReadRules) return null;

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
