'use client';

import { useMemo, useState } from 'react';
import { Archive, Building2, History, Search, Zap } from 'lucide-react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { hasPermission, usePermissions } from '@/hooks/usePermissions';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';
import { formatDateTime } from '@/lib/localization';
import type { ArchivedSiteItem, RetiredChargerItem, SiteListItem } from '@/types';

const PAGE_SIZE = 50;
const FETCH_LIMIT = PAGE_SIZE + 1;

interface Filters {
  search: string;
  fromDate: string;
  toDate: string;
  originalSiteId: string;
}

const EMPTY_FILTERS: Filters = {
  search: '',
  fromDate: '',
  toDate: '',
  originalSiteId: 'all',
};

function dateBoundary(value: string, endOfDay: boolean): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  return `${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}Z`;
}

function operatorName(actor: { username?: string | null; full_name?: string | null } | null | undefined, fallback: string) {
  return actor?.full_name?.trim() || actor?.username?.trim() || fallback;
}

export default function AssetArchivePage() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const { permissions, isLoading: permissionsLoading } = usePermissions();
  const canReadSites = hasPermission(permissions, 'sites.read');
  const canReadChargers = hasPermission(permissions, 'chargers.read');
  const [selectedTab, setSelectedTab] = useState<'sites' | 'chargers'>('sites');
  const activeTab = selectedTab === 'sites'
    ? (canReadSites ? 'sites' : 'chargers')
    : (canReadChargers ? 'chargers' : 'sites');
  const [draftFilters, setDraftFilters] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [siteOffset, setSiteOffset] = useState(0);
  const [chargerOffset, setChargerOffset] = useState(0);

  const siteUrl = useMemo(() => {
    if (!canReadSites) return null;
    const params = new URLSearchParams({ limit: String(FETCH_LIMIT), offset: String(siteOffset) });
    if (filters.search.trim()) params.set('search', filters.search.trim().slice(0, 200));
    const from = dateBoundary(filters.fromDate, false);
    const to = dateBoundary(filters.toDate, true);
    if (from) params.set('archived_from', from);
    if (to) params.set('archived_to', to);
    return `${API_ENDPOINTS.ASSET_ARCHIVE_SITES}?${params.toString()}`;
  }, [canReadSites, filters, siteOffset]);

  const chargerUrl = useMemo(() => {
    if (!canReadChargers) return null;
    const params = new URLSearchParams({ limit: String(FETCH_LIMIT), offset: String(chargerOffset) });
    if (filters.search.trim()) params.set('search', filters.search.trim().slice(0, 200));
    if (filters.originalSiteId !== 'all') params.set('original_site_id', filters.originalSiteId);
    const from = dateBoundary(filters.fromDate, false);
    const to = dateBoundary(filters.toDate, true);
    if (from) params.set('retired_from', from);
    if (to) params.set('retired_to', to);
    return `${API_ENDPOINTS.ASSET_ARCHIVE_CHARGERS}?${params.toString()}`;
  }, [canReadChargers, chargerOffset, filters]);

  const { data: archivedSites, error: sitesError, isLoading: sitesLoading } = useSWR<ArchivedSiteItem[]>(
    siteUrl,
    (url: string) => apiGet<ArchivedSiteItem[]>(url),
    { keepPreviousData: true }
  );
  const { data: retiredChargers, error: chargersError, isLoading: chargersLoading } = useSWR<RetiredChargerItem[]>(
    chargerUrl,
    (url: string) => apiGet<RetiredChargerItem[]>(url),
    { keepPreviousData: true }
  );
  const { data: siteOptions } = useSWR<SiteListItem[]>(
    canReadSites && canReadChargers ? `${API_ENDPOINTS.SITES}?include_inactive=true&limit=1000` : null,
    (url: string) => apiGet<SiteListItem[]>(url)
  );

  const visibleSites = (archivedSites || []).slice(0, PAGE_SIZE);
  const visibleChargers = (retiredChargers || []).slice(0, PAGE_SIZE);
  const siteHasNext = (archivedSites?.length || 0) > PAGE_SIZE;
  const chargerHasNext = (retiredChargers?.length || 0) > PAGE_SIZE;

  const applyFilters = () => {
    if (draftFilters.fromDate && draftFilters.toDate && draftFilters.fromDate > draftFilters.toDate) {
      setFilterError(t('archive.invalidDateRange'));
      return;
    }
    setFilterError(null);
    setFilters({ ...draftFilters, search: draftFilters.search.trim() });
    setSiteOffset(0);
    setChargerOffset(0);
  };

  const clearFilters = () => {
    setDraftFilters(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setFilterError(null);
    setSiteOffset(0);
    setChargerOffset(0);
  };

  if (!permissionsLoading && !canReadSites && !canReadChargers) {
    return (
      <Card className="border-slate-700 bg-slate-800/80">
        <CardContent className="py-12 text-center text-slate-300">{t('archive.noPermission')}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-3 text-3xl font-bold text-white">
          <Archive className="h-8 w-8 text-purple-400" />
          {t('archive.title')}
        </h1>
        <p className="mt-1 text-slate-400">{t('archive.subtitle')}</p>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setSelectedTab(value as 'sites' | 'chargers')} className="space-y-5">
        <TabsList className="border border-slate-700 bg-slate-800/80">
          {canReadSites && <TabsTrigger value="sites">{t('archive.sitesTab')}</TabsTrigger>}
          {canReadChargers && <TabsTrigger value="chargers">{t('archive.chargersTab')}</TabsTrigger>}
        </TabsList>

        <Card className="border-slate-700 bg-slate-800/80">
          <CardContent className="space-y-4 pt-6">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2 xl:col-span-2">
                <Label htmlFor="archive-search" className="text-slate-300">{t('search')}</Label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                  <Input
                    id="archive-search"
                    data-testid="archive-search"
                    value={draftFilters.search}
                    onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))}
                    placeholder={t('archive.search')}
                    className="border-slate-600 bg-slate-700/50 pl-9 text-slate-100"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="archive-from" className="text-slate-300">{t('archive.fromDate')}</Label>
                <Input
                  id="archive-from"
                  data-testid="archive-from"
                  type="date"
                  value={draftFilters.fromDate}
                  onChange={(event) => setDraftFilters((current) => ({ ...current, fromDate: event.target.value }))}
                  className="border-slate-600 bg-slate-700/50 text-slate-100"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="archive-to" className="text-slate-300">{t('archive.toDate')}</Label>
                <Input
                  id="archive-to"
                  data-testid="archive-to"
                  type="date"
                  value={draftFilters.toDate}
                  onChange={(event) => setDraftFilters((current) => ({ ...current, toDate: event.target.value }))}
                  className="border-slate-600 bg-slate-700/50 text-slate-100"
                />
              </div>
            </div>

            {activeTab === 'chargers' && canReadChargers && (
              <div className="max-w-md space-y-2">
                <Label className="text-slate-300">{t('archive.originalSite')}</Label>
                {canReadSites ? (
                  <Select
                    value={draftFilters.originalSiteId}
                    onValueChange={(value) => setDraftFilters((current) => ({ ...current, originalSiteId: value }))}
                  >
                    <SelectTrigger data-testid="archive-original-site" className="border-slate-600 bg-slate-700/50 text-slate-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('archive.allSites')}</SelectItem>
                      {(siteOptions || []).map((site) => (
                        <SelectItem key={site.id} value={site.id}>{site.name} · {site.site_code}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    data-testid="archive-original-site-id"
                    value={draftFilters.originalSiteId === 'all' ? '' : draftFilters.originalSiteId}
                    onChange={(event) => setDraftFilters((current) => ({
                      ...current,
                      originalSiteId: event.target.value.trim() || 'all',
                    }))}
                    placeholder={t('archive.originalSite')}
                    className="border-slate-600 bg-slate-700/50 text-slate-100"
                  />
                )}
              </div>
            )}

            {filterError && <p role="alert" className="text-sm text-red-300">{filterError}</p>}
            <div className="flex flex-wrap gap-3">
              <Button data-testid="archive-apply" type="button" onClick={applyFilters}>{t('archive.apply')}</Button>
              <Button type="button" variant="outline" onClick={clearFilters}>{t('archive.clear')}</Button>
            </div>
          </CardContent>
        </Card>

        {canReadSites && (
          <TabsContent value="sites">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader><CardTitle className="text-white">{t('archive.sitesTab')}</CardTitle></CardHeader>
              <CardContent>
                {sitesLoading && !archivedSites ? (
                  <p className="py-10 text-center text-slate-400">{t('archive.loading')}</p>
                ) : sitesError ? (
                  <p role="alert" className="py-10 text-center text-red-300">{t('archive.loadFailed')}</p>
                ) : visibleSites.length === 0 ? (
                  <p className="py-10 text-center text-slate-400">{t('archive.emptySites')}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead><tr className="border-b border-slate-700">
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.site')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.retiredChargers')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.reason')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.operator')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.time')}</th>
                        <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">{t('操作')}</th>
                      </tr></thead>
                      <tbody>{visibleSites.map((site) => (
                        <tr key={site.id} data-testid="archived-site-row" className="border-b border-slate-700/50">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <Building2 className="h-5 w-5 text-amber-400" />
                              <div><p className="font-medium text-white">{site.name}</p><p className="text-xs text-slate-400">{site.site_code} · {site.address}</p></div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-slate-200">{site.retired_charge_points_count}</td>
                          <td className="max-w-xs px-4 py-3 text-sm text-slate-300">{site.archive_reason || t('common.notAvailable')}</td>
                          <td className="px-4 py-3 text-sm text-slate-300">{operatorName(site.archived_by, t('common.notAvailable'))}</td>
                          <td className="px-4 py-3 text-sm text-slate-300">{formatDateTime(site.archived_at, locale, t('common.notAvailable'))}</td>
                          <td className="px-4 py-3 text-right"><Button size="sm" variant="outline" onClick={() => router.push(`/sites/${site.id}`)}>{t('archive.details')}</Button></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                <div className="mt-4 flex items-center justify-end gap-3">
                  <Button variant="outline" disabled={siteOffset === 0} onClick={() => setSiteOffset(Math.max(0, siteOffset - PAGE_SIZE))}>{t('archive.previous')}</Button>
                  <Badge variant="outline">{t('archive.page').replace('{page}', String(Math.floor(siteOffset / PAGE_SIZE) + 1))}</Badge>
                  <Button variant="outline" disabled={!siteHasNext} onClick={() => setSiteOffset(siteOffset + PAGE_SIZE)}>{t('archive.next')}</Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {canReadChargers && (
          <TabsContent value="chargers">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader><CardTitle className="text-white">{t('archive.chargersTab')}</CardTitle></CardHeader>
              <CardContent>
                {chargersLoading && !retiredChargers ? (
                  <p className="py-10 text-center text-slate-400">{t('archive.loading')}</p>
                ) : chargersError ? (
                  <p role="alert" className="py-10 text-center text-red-300">{t('archive.loadFailed')}</p>
                ) : visibleChargers.length === 0 ? (
                  <p className="py-10 text-center text-slate-400">{t('archive.emptyChargers')}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead><tr className="border-b border-slate-700">
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.charger')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.originalSite')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.reason')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.operator')}</th>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">{t('archive.time')}</th>
                        <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">{t('操作')}</th>
                      </tr></thead>
                      <tbody>{visibleChargers.map((charger) => (
                        <tr key={charger.id} data-testid="retired-charger-row" className="border-b border-slate-700/50">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <Zap className="h-5 w-5 text-amber-400" />
                              <div><p className="font-medium text-white">{charger.display_name || charger.display_code}</p><p className="text-xs text-slate-400">{charger.display_code} · {charger.ocpp_identity}</p></div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-sm text-slate-300">{charger.original_site.name}<p className="text-xs text-slate-500">{charger.original_site.site_code}</p></td>
                          <td className="max-w-xs px-4 py-3 text-sm text-slate-300">{charger.retirement_reason || t('common.notAvailable')}</td>
                          <td className="px-4 py-3 text-sm text-slate-300">{operatorName(charger.retired_by, t('common.notAvailable'))}</td>
                          <td className="px-4 py-3 text-sm text-slate-300">{formatDateTime(charger.retired_at, locale, t('common.notAvailable'))}</td>
                          <td className="px-4 py-3"><div className="flex justify-end gap-2">
                            <Button size="sm" variant="outline" onClick={() => router.push(`/chargers/${charger.id}`)}>{t('archive.details')}</Button>
                            <Button size="sm" variant="outline" onClick={() => router.push(`/transactions?charge_point_id=${encodeURIComponent(charger.ocpp_identity)}`)}><History className="h-4 w-4" />{t('archive.history')}</Button>
                          </div></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                <div className="mt-4 flex items-center justify-end gap-3">
                  <Button variant="outline" disabled={chargerOffset === 0} onClick={() => setChargerOffset(Math.max(0, chargerOffset - PAGE_SIZE))}>{t('archive.previous')}</Button>
                  <Badge variant="outline">{t('archive.page').replace('{page}', String(Math.floor(chargerOffset / PAGE_SIZE) + 1))}</Badge>
                  <Button variant="outline" disabled={!chargerHasNext} onClick={() => setChargerOffset(chargerOffset + PAGE_SIZE)}>{t('archive.next')}</Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
