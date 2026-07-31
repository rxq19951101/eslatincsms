'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { Download, Search } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';

import ChargingRecordsTable from '@/components/transactions/ChargingRecordsTable';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS, REFRESH_INTERVAL } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';
import type { ChargingRecord, PaginatedResponse, SiteListItem } from '@/types';

const PAGE_SIZES = [25, 50, 100] as const;

function useDebouncedValue<T>(value: T, delay = 350): T {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedValue(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debouncedValue;
}

function dateBoundary(value: string, endOfDay: boolean): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  return `${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}Z`;
}

function TransactionsPageContent() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const linkedChargerReference = searchParams.get('charge_point_id')?.slice(0, 100) || '';
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearch = useDebouncedValue(searchQuery.trim());
  const [statusFilter, setStatusFilter] = useState('all');
  const [paymentStatusFilter, setPaymentStatusFilter] = useState('all');
  const [siteFilter, setSiteFilter] = useState('all');
  const [chargerFilter, setChargerFilter] = useState(linkedChargerReference);
  const debouncedChargerFilter = useDebouncedValue(chargerFilter.trim());
  const [startedFrom, setStartedFrom] = useState('');
  const [startedTo, setStartedTo] = useState('');
  const [limit, setLimit] = useState<number>(50);
  const [offset, setOffset] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const filters = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedSearch) params.set('search', debouncedSearch.slice(0, 100));
    if (statusFilter !== 'all') params.set('status', statusFilter);
    if (paymentStatusFilter !== 'all') params.set('payment_status', paymentStatusFilter);
    if (siteFilter !== 'all') params.set('site_id', siteFilter);
    if (debouncedChargerFilter) params.set('charge_point_id', debouncedChargerFilter.slice(0, 100));
    const from = dateBoundary(startedFrom, false);
    const to = dateBoundary(startedTo, true);
    if (from) params.set('started_from', from);
    if (to) params.set('started_to', to);
    return params;
  }, [debouncedChargerFilter, debouncedSearch, paymentStatusFilter, siteFilter, startedFrom, startedTo, statusFilter]);

  const listUrl = useMemo(() => {
    const params = new URLSearchParams(filters);
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    return `${API_ENDPOINTS.TRANSACTIONS}?${params.toString()}`;
  }, [filters, limit, offset]);

  const { data, error, isLoading } = useSWR<PaginatedResponse<ChargingRecord>>(
    listUrl,
    (url: string) => apiGet<PaginatedResponse<ChargingRecord>>(url),
    { keepPreviousData: true, refreshInterval: REFRESH_INTERVAL },
  );
  const { data: sites } = useSWR<SiteListItem[]>(
    API_ENDPOINTS.SITES,
    (url: string) => apiGet<SiteListItem[]>(url),
    { refreshInterval: REFRESH_INTERVAL },
  );

  const total = typeof data?.total === 'number' && Number.isFinite(data.total) ? data.total : 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.min(totalPages, Math.floor(offset / limit) + 1);

  const resetPage = () => setOffset(0);

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const query = filters.toString();
      const csv = await apiGet<string>(`${API_ENDPOINTS.TRANSACTIONS_EXPORT}${query ? `?${query}` : ''}`);
      const csvWithBom = csv.startsWith('\uFEFF') ? csv : `\uFEFF${csv}`;
      const blob = new Blob([csvWithBom], { type: 'text/csv;charset=utf-8' });
      const href = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = `charging-records-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch {
      setExportError(t('transactions.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('transactions.title')}</h1>
          <p className="mt-1 text-slate-400">{t('transactions.subtitle')}</p>
        </div>
        <Button
          onClick={handleExport}
          disabled={exporting}
          className="bg-gradient-to-r from-purple-600 to-blue-600"
        >
          <Download className="mr-2 h-4 w-4" />
          {t(exporting ? 'transactions.exporting' : 'transactions.export')}
        </Button>
      </div>

      <Card className="border-slate-700 bg-slate-800/80 backdrop-blur-sm">
        <CardContent className="space-y-4 pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              type="search"
              maxLength={100}
              aria-label={t('transactions.searchPlaceholder')}
              placeholder={t('transactions.searchPlaceholder')}
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                resetPage();
              }}
              className="border-slate-600 bg-slate-700/50 pl-10"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Select value={statusFilter} onValueChange={(value) => { setStatusFilter(value); resetPage(); }}>
              <SelectTrigger className="border-slate-600 bg-slate-700/50" aria-label={t('transactions.sessionStatus')}>
                <SelectValue placeholder={t('transactions.sessionStatus')} />
              </SelectTrigger>
              <SelectContent className="border-slate-700 bg-slate-800">
                <SelectItem value="all">{t('transactions.allSessionStatuses')}</SelectItem>
                <SelectItem value="ongoing">{t('status.ongoing')}</SelectItem>
                <SelectItem value="completed">{t('status.completed')}</SelectItem>
                <SelectItem value="cancelled">{t('status.cancelled')}</SelectItem>
              </SelectContent>
            </Select>

            <Select value={paymentStatusFilter} onValueChange={(value) => { setPaymentStatusFilter(value); resetPage(); }}>
              <SelectTrigger className="border-slate-600 bg-slate-700/50" aria-label={t('transactions.paymentStatus')}>
                <SelectValue placeholder={t('transactions.paymentStatus')} />
              </SelectTrigger>
              <SelectContent className="border-slate-700 bg-slate-800">
                <SelectItem value="all">{t('transactions.allPaymentStatuses')}</SelectItem>
                <SelectItem value="created">{t('transactions.payment.created')}</SelectItem>
                <SelectItem value="pending">{t('transactions.payment.pending')}</SelectItem>
                <SelectItem value="processing">{t('transactions.payment.processing')}</SelectItem>
                <SelectItem value="approved">{t('transactions.payment.paid')}</SelectItem>
                <SelectItem value="paid">{t('transactions.payment.paid')}</SelectItem>
                <SelectItem value="declined">{t('transactions.payment.declined')}</SelectItem>
                <SelectItem value="voided">{t('transactions.payment.voided')}</SelectItem>
                <SelectItem value="error">{t('transactions.payment.failed')}</SelectItem>
                <SelectItem value="expired">{t('transactions.payment.expired')}</SelectItem>
                <SelectItem value="refunded">{t('transactions.payment.refunded')}</SelectItem>
                <SelectItem value="unpaid">{t('transactions.payment.unpaid')}</SelectItem>
                <SelectItem value="cancelled">{t('transactions.payment.cancelled')}</SelectItem>
              </SelectContent>
            </Select>

            <Select value={siteFilter} onValueChange={(value) => { setSiteFilter(value); resetPage(); }}>
              <SelectTrigger className="border-slate-600 bg-slate-700/50" aria-label={t('transactions.site')}>
                <SelectValue placeholder={t('transactions.site')} />
              </SelectTrigger>
              <SelectContent className="border-slate-700 bg-slate-800">
                <SelectItem value="all">{t('transactions.allSites')}</SelectItem>
                {(sites || []).map((site) => (
                  <SelectItem key={site.site_code} value={site.site_code}>{site.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Input
              maxLength={100}
              aria-label={t('transactions.chargerFilter')}
              placeholder={t('transactions.chargerFilter')}
              value={chargerFilter}
              onChange={(event) => {
                setChargerFilter(event.target.value);
                resetPage();
              }}
              className="border-slate-600 bg-slate-700/50"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm text-slate-400">
              <span>{t('transactions.startDate')}</span>
              <Input
                type="date"
                value={startedFrom}
                max={startedTo || undefined}
                onChange={(event) => { setStartedFrom(event.target.value); resetPage(); }}
                className="border-slate-600 bg-slate-700/50 text-slate-100"
              />
            </label>
            <label className="space-y-1 text-sm text-slate-400">
              <span>{t('transactions.endDate')}</span>
              <Input
                type="date"
                value={startedTo}
                min={startedFrom || undefined}
                onChange={(event) => { setStartedTo(event.target.value); resetPage(); }}
                className="border-slate-600 bg-slate-700/50 text-slate-100"
              />
            </label>
          </div>
          {exportError && <p role="alert" className="text-sm text-red-400">{exportError}</p>}
        </CardContent>
      </Card>

      <Card className="border-slate-700 bg-slate-800/80 backdrop-blur-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <CardTitle className="text-white">{t('transactions.list')}</CardTitle>
          <Select
            value={String(limit)}
            onValueChange={(value) => {
              const parsed = Number(value);
              setLimit(Number.isFinite(parsed) ? parsed : 50);
              resetPage();
            }}
          >
            <SelectTrigger className="w-[150px] border-slate-600 bg-slate-700/50" aria-label={t('transactions.pageSize')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800">
              {PAGE_SIZES.map((size) => (
                <SelectItem key={size} value={String(size)}>{size} {t('transactions.perPage')}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          {isLoading && !data ? (
            <div className="py-12 text-center text-slate-400">{t('transactions.loading')}</div>
          ) : error ? (
            <div role="alert" className="py-12 text-center text-red-400">{t('transactions.loadFailed')}</div>
          ) : (
            <ChargingRecordsTable records={Array.isArray(data?.items) ? data.items : []} />
          )}

          {!error && total > 0 && (
            <div className="mt-5 flex flex-col gap-3 border-t border-slate-700 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-400">
                {t('transactions.page')} {currentPage} {t('transactions.of')} {totalPages} · {t('transactions.total')} {total} {t('transactions.records')}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  disabled={offset <= 0}
                  onClick={() => setOffset((value) => Math.max(0, value - limit))}
                >
                  {t('transactions.previous')}
                </Button>
                <Button
                  variant="outline"
                  disabled={offset + limit >= total}
                  onClick={() => setOffset((value) => value + limit)}
                >
                  {t('transactions.next')}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function TransactionsPage() {
  return (
    <Suspense fallback={<TransactionsPageFallback />}>
      <TransactionsPageContent />
    </Suspense>
  );
}

function TransactionsPageFallback() {
  const { t } = useI18n();
  return <div className="py-12 text-center text-slate-400">{t('transactions.loading')}</div>;
}
