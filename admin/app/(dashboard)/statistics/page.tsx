'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { isOperationalSite } from '@/lib/assetLifecycle';
import type { SiteListItem, TrendDataPoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LocalizedDateInput } from '@/components/ui/localized-date-input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Download, RefreshCw } from 'lucide-react';
import { TrendChart } from '@/features/dashboard/TrendChart';
import { useI18n } from '@/lib/i18n';

const fetcher = <T,>(url: string) => apiGet<T>(url);
const RANGE_OPTIONS = [7, 30, 90] as const;
type RangeOption = (typeof RANGE_OPTIONS)[number] | 'custom';
type ReportType = 'revenue' | 'energy' | 'orders';

interface RevenueStat {
  date: string;
  total_revenue: string;
  total_energy_kwh: string;
  invoice_count: number;
  currency: 'COP';
}

interface EnergyStat {
  date: string;
  total_energy_kwh: string;
  session_count: number;
}

interface OrdersStat {
  date: string;
  order_count: number;
  completed_count: number;
}

interface ReportCardProps {
  title: string;
  description: string;
  chartTitle: string;
  data: TrendDataPoint[];
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  color: string;
  unit?: string;
  valueFormatter?: (value: number) => string;
  className?: string;
}

function dateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function defaultStartDate(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - (days - 1));
  return dateInputValue(date);
}

function decimalToNumber(value: string | number): number | null {
  const numericValue = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function chartData<T>(items: T[] | undefined, dateOf: (item: T) => string, valueOf: (item: T) => string | number): TrendDataPoint[] {
  return (items ?? []).flatMap((item) => {
    const value = decimalToNumber(valueOf(item));
    return value === null ? [] : [{ date: dateOf(item), value }];
  });
}

function ReportCard({
  title,
  description,
  chartTitle,
  data,
  isLoading,
  error,
  onRetry,
  color,
  unit,
  valueFormatter,
  className = '',
}: ReportCardProps) {
  const { t } = useI18n();

  return (
    <Card className={`bg-slate-800/80 backdrop-blur-sm border-slate-700 ${className}`}>
      <CardHeader>
        <CardTitle className="text-white">{title}</CardTitle>
        <p className="text-sm text-slate-400">{description}</p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-slate-400">{t('reports.loading')}</div>
        ) : error ? (
          <div className="h-64 flex flex-col items-center justify-center gap-4 text-center">
            <p className="text-red-300">{t('reports.loadFailed')}</p>
            <Button type="button" variant="outline" onClick={onRetry}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('reports.retry')}
            </Button>
          </div>
        ) : data.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-slate-400">{t('reports.empty')}</div>
        ) : (
          <div className="h-64">
            <TrendChart
              data={data}
              title={chartTitle}
              color={color}
              unit={unit}
              valueFormatter={valueFormatter}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function StatisticsPage() {
  const { locale, t } = useI18n();
  const [range, setRange] = useState<RangeOption>(30);
  const [startDate, setStartDate] = useState(defaultStartDate(30));
  const [endDate, setEndDate] = useState(dateInputValue(new Date()));
  const [siteId, setSiteId] = useState('all');
  const [reportType, setReportType] = useState<ReportType>('revenue');
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState(false);

  const customRangeIsValid = range !== 'custom'
    || (Boolean(startDate) && Boolean(endDate) && startDate <= endDate);

  const sharedQuery = useMemo(() => {
    if (!customRangeIsValid) return null;

    const params = new URLSearchParams({ group_by: 'day' });
    if (range === 'custom') {
      params.set('start_date', startDate);
      params.set('end_date', endDate);
    } else {
      params.set('days', String(range));
    }
    if (siteId !== 'all') params.set('site_id', siteId);
    return params.toString();
  }, [customRangeIsValid, endDate, range, siteId, startDate]);

  const { data: sites, error: sitesError, isLoading: sitesLoading, mutate: retrySites } = useSWR<SiteListItem[]>(
    API_ENDPOINTS.SITES_ACTIVE,
    fetcher
  );

  const {
    data: revenueData,
    error: revenueError,
    isLoading: revenueLoading,
    mutate: retryRevenue,
  } = useSWR<RevenueStat[]>(
    sharedQuery ? `${API_ENDPOINTS.STATISTICS_REVENUE}?${sharedQuery}` : null,
    fetcher
  );

  const {
    data: energyData,
    error: energyError,
    isLoading: energyLoading,
    mutate: retryEnergy,
  } = useSWR<EnergyStat[]>(
    sharedQuery ? `${API_ENDPOINTS.STATISTICS_ENERGY}?${sharedQuery}` : null,
    fetcher
  );

  const {
    data: ordersData,
    error: ordersError,
    isLoading: ordersLoading,
    mutate: retryOrders,
  } = useSWR<OrdersStat[]>(
    sharedQuery ? `${API_ENDPOINTS.STATISTICS_ORDERS}?${sharedQuery}` : null,
    fetcher
  );

  const revenueChartData = useMemo(
    () => chartData(revenueData, (item) => item.date, (item) => item.total_revenue),
    [revenueData]
  );
  const energyChartData = useMemo(
    () => chartData(energyData, (item) => item.date, (item) => item.total_energy_kwh),
    [energyData]
  );
  const ordersChartData = useMemo(
    () => chartData(ordersData, (item) => item.date, (item) => item.order_count),
    [ordersData]
  );

  const copFormatter = useMemo(() => new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 2,
  }), [locale]);

  const rangeDescription = range === 'custom'
    ? `${startDate} – ${endDate}`
    : t(`reports.last${range}Days`);

  const handleExport = async () => {
    if (!sharedQuery || isExporting) return;
    setIsExporting(true);
    setExportError(false);

    try {
      const params = new URLSearchParams(sharedQuery);
      params.set('report_type', reportType);
      params.set('format', 'csv');
      const csv = await apiGet<string>(`${API_ENDPOINTS.STATISTICS_EXPORT}?${params.toString()}`, {
        headers: { Accept: 'text/csv' },
      });
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      const rangeLabel = range === 'custom' ? `${startDate}_${endDate}` : `${range}days`;
      anchor.href = url;
      anchor.download = `${reportType}_${rangeLabel}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Report export failed:', error);
      setExportError(true);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">{t('reports.title')}</h1>
        <p className="mt-1 text-slate-400">{t('reports.subtitle')}</p>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="space-y-5 pt-6">
          <div className="flex flex-wrap gap-2" aria-label={t('reports.dateRange')}>
            {RANGE_OPTIONS.map((days) => (
              <Button
                key={days}
                type="button"
                variant={range === days ? 'default' : 'outline'}
                onClick={() => setRange(days)}
              >
                {t(`reports.last${days}Days`)}
              </Button>
            ))}
            <Button
              type="button"
              variant={range === 'custom' ? 'default' : 'outline'}
              onClick={() => setRange('custom')}
            >
              {t('reports.customRange')}
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {range === 'custom' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="report-start-date">{t('reports.startDate')}</Label>
                  <LocalizedDateInput
                    id="report-start-date"
                    aria-label={t('reports.startDate')}
                    testId="reports-start-date"
                    value={startDate}
                    max={endDate || undefined}
                    onChange={setStartDate}
                    className="bg-slate-900/60 border-slate-700"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="report-end-date">{t('reports.endDate')}</Label>
                  <LocalizedDateInput
                    id="report-end-date"
                    aria-label={t('reports.endDate')}
                    testId="reports-end-date"
                    value={endDate}
                    min={startDate || undefined}
                    onChange={setEndDate}
                    className="bg-slate-900/60 border-slate-700"
                  />
                </div>
              </>
            )}

            <div className="space-y-2">
              <Label>{t('reports.site')}</Label>
              <Select value={siteId} onValueChange={setSiteId} disabled={sitesLoading}>
                <SelectTrigger className="bg-slate-900/60 border-slate-700">
                  <SelectValue placeholder={t('reports.allSites')} />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="all">{t('reports.allSites')}</SelectItem>
                  {(sites ?? []).filter(isOperationalSite).map((site) => (
                    <SelectItem key={site.id} value={site.id}>{site.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {sitesLoading && <p className="text-xs text-slate-400">{t('reports.loadingSites')}</p>}
              {sitesError && (
                <div className="flex items-center gap-2 text-xs text-red-300">
                  <span>{t('reports.sitesLoadFailed')}</span>
                  <button type="button" className="underline" onClick={() => retrySites()}>{t('reports.retry')}</button>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label>{t('reports.exportType')}</Label>
              <Select value={reportType} onValueChange={(value) => setReportType(value as ReportType)}>
                <SelectTrigger className="bg-slate-900/60 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="revenue">{t('reports.revenue')}</SelectItem>
                  <SelectItem value="energy">{t('reports.energy')}</SelectItem>
                  <SelectItem value="orders">{t('reports.orders')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end">
              <Button
                type="button"
                onClick={handleExport}
                disabled={!sharedQuery || isExporting}
                className="w-full bg-gradient-to-r from-purple-600 to-blue-600"
              >
                <Download className="mr-2 h-4 w-4" />
                {isExporting ? t('reports.exporting') : t('reports.export')}
              </Button>
            </div>
          </div>

          {!customRangeIsValid && <p className="text-sm text-red-300">{t('reports.invalidDateRange')}</p>}
          {exportError && (
            <div className="flex items-center gap-3 text-sm text-red-300">
              <span>{t('reports.exportFailed')}</span>
              <button type="button" className="underline" onClick={handleExport}>{t('reports.retry')}</button>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ReportCard
          title={t('reports.revenueReport')}
          description={rangeDescription}
          chartTitle={t('reports.revenue')}
          data={revenueChartData}
          isLoading={revenueLoading}
          error={revenueError}
          onRetry={() => retryRevenue()}
          color="hsl(var(--chart-primary))"
          unit="COP"
          valueFormatter={(value) => copFormatter.format(value)}
        />

        <ReportCard
          title={t('reports.energyReport')}
          description={rangeDescription}
          chartTitle={t('reports.energy')}
          data={energyChartData}
          isLoading={energyLoading}
          error={energyError}
          onRetry={() => retryEnergy()}
          color="hsl(var(--chart-secondary))"
          unit="kWh"
        />

        <ReportCard
          title={t('reports.ordersReport')}
          description={rangeDescription}
          chartTitle={t('reports.orders')}
          data={ordersChartData}
          isLoading={ordersLoading}
          error={ordersError}
          onRetry={() => retryOrders()}
          color="hsl(var(--chart-accent))"
          className="lg:col-span-2"
        />
      </div>
    </div>
  );
}
