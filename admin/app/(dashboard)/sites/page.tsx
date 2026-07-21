'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import type { SiteListItem } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Building2, MapPin, Plus } from 'lucide-react';
import GooglePlacesAutocomplete from '@/components/sites/GooglePlacesAutocomplete';
import { useI18n } from '@/lib/i18n';
import { matchesSearchQuery } from '@/lib/search';
import {
  apiErrorMessageKey,
  apiFieldErrors,
  fieldErrors,
  siteSchema,
  SITE_API_FIELD_MAPPING,
  type FieldErrors,
} from '@/lib/validation';

function MapLoading() {
  const { t } = useI18n();
  return (
    <div className="h-[400px] bg-slate-800/50 animate-pulse rounded-md flex items-center justify-center">
      <span className="text-slate-400 text-sm">{t('加载地图中...')}</span>
    </div>
  );
}

// 动态导入地图组件（避免 SSR 错误）
const GoogleMapView = dynamic(() => import('@/components/map/GoogleMapView'), {
  ssr: false,
  loading: () => <MapLoading />
});

const fetcher = (url: string) => apiGet<SiteListItem[]>(url);

export default function SitesPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});

  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [latitude, setLatitude] = useState('4.6097');
  const [longitude, setLongitude] = useState('-74.0817');
  const [operatingHours, setOperatingHours] = useState('');

  const { data: sites, error, isLoading, mutate } = useSWR<SiteListItem[]>(
    API_ENDPOINTS.SITES,
    fetcher,
    { refreshInterval: 30000 }
  );

  const filtered = useMemo(() => {
    const list = sites || [];
    return list.filter((site) => matchesSearchQuery(searchQuery, [site.name, site.address]));
  }, [sites, searchQuery]);

  const handleCreate = async () => {
    setErrorText(null);
    const result = siteSchema.safeParse({
      name,
      address,
      latitude,
      longitude,
      operating_hours: operatingHours,
    });
    if (!result.success) {
      setErrors(fieldErrors(result.error));
      return;
    }
    setErrors({});

    setSubmitting(true);
    try {
      await apiPost(API_ENDPOINTS.SITES, {
        ...result.data,
        operating_hours: result.data.operating_hours || null,
        is_active: true,
      });
      setOpen(false);
      setName('');
      setAddress('');
      setOperatingHours('');
      mutate();
    } catch (e) {
      setErrors(apiFieldErrors(e, SITE_API_FIELD_MAPPING));
      setErrorText(t(apiErrorMessageKey(e, '创建失败')));
    } finally {
      setSubmitting(false);
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('站点管理')}</h1>
          <p className="text-slate-400 mt-1">{t('以站点为单位管理充电桩与运营数据')}</p>
        </div>
        <Button
          data-testid="admin-site-create-open"
          onClick={() => {
            setErrorText(null);
            setErrors({});
            setOpen(true);
          }}
          className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
        >
          <Plus className="h-4 w-4 mr-2" />
          {t('新增站点')}
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <Input
                data-testid="admin-site-search"
                type="text"
                placeholder={t('搜索站点名称/地址...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-700/50 border-slate-600 text-slate-200 placeholder:text-slate-500"
              />
            </div>
            <div className="text-sm text-slate-400 flex items-center">
              {t(`共 ${filtered.length} 个站点`)}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('站点列表')}</CardTitle>
        </CardHeader>
        <CardContent>
          {filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('站点')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('地址')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('充电桩')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('在线')}</th>
                    <th className="text-right py-3 px-4 text-slate-400 font-medium">{t('操作')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => (
                    <tr
                      key={s.id}
                      data-testid="admin-site-row"
                      data-site-code={s.site_code}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                      onClick={() => router.push(`/sites/${encodeURIComponent(s.id)}`)}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-gradient-to-br from-purple-600/20 to-blue-600/20 rounded-lg">
                            <Building2 className="h-5 w-5 text-purple-400" />
                          </div>
                          <div>
                            <div className="text-white font-medium">{t(s.name)}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        <div className="flex items-center gap-2">
                          <MapPin className="h-4 w-4 text-slate-500" />
                          {s.address}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-300">{s.charge_points_count}</td>
                      <td className="py-3 px-4 text-slate-300">{s.online_charge_points_count ?? 0}</td>
                      <td className="py-3 px-4 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/sites/${encodeURIComponent(s.id)}`);
                          }}
                          className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
                        >
                          {t('详情')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12">
              <Building2 className="h-12 w-12 text-slate-500 mx-auto mb-4" />
              <p className="text-slate-400">{t('暂无站点')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="admin-site-create-dialog" className="bg-slate-900 border-slate-700 text-slate-100">
          <DialogHeader>
            <DialogTitle className="text-white">{t('新增站点')}</DialogTitle>
            <DialogDescription className="text-slate-400">{t('创建一个新的运营站点。')}</DialogDescription>
          </DialogHeader>

          {errorText && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {errorText}
            </div>
          )}

          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            <div className="space-y-2">
              <Label className="text-slate-300">{t('站点名称 *')}</Label>
              <Input
                data-testid="admin-site-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={!!errors.name}
                className="bg-slate-800 border-slate-600 text-slate-200"
              />
              {errors.name && <p className="text-sm text-red-400">{t(errors.name)}</p>}
            </div>
            
            <div className="space-y-2">
              <Label className="text-slate-300">{t('地址 *')}</Label>
              <GooglePlacesAutocomplete
                value={address}
                onChange={setAddress}
                onSelect={(result) => {
                  setAddress(result.address);
                  setLatitude(String(result.lat));
                  setLongitude(String(result.lng));
                }}
                placeholder={t('搜索地址（自动填充经纬度）')}
                className="bg-slate-800 border-slate-600 text-slate-200"
                inputTestId="admin-site-address"
              />
              {errors.address && <p className="text-sm text-red-400">{t(errors.address)}</p>}
            </div>

            <div className="space-y-2">
              <Label className="text-slate-300">{t('地图选点')}</Label>
              <GoogleMapView
                center={
                  latitude && longitude && !isNaN(Number(latitude)) && !isNaN(Number(longitude))
                    ? { lat: Number(latitude), lng: Number(longitude) }
                    : { lat: 4.6097, lng: -74.0817 }
                }
                markers={
                  latitude && longitude && !isNaN(Number(latitude)) && !isNaN(Number(longitude))
                    ? [{ lat: Number(latitude), lng: Number(longitude), title: name || t('新站点') }]
                    : []
                }
                onClick={(lat, lng) => {
                  setLatitude(String(lat));
                  setLongitude(String(lng));
                }}
                height="400px"
                zoom={13}
              />
              <p className="text-xs text-slate-400 mt-1">
                {t('提示：搜索地址后自动定位，也可点击地图任意位置更新坐标')}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">{t('纬度 *')}</Label>
                <Input
                  data-testid="admin-site-latitude"
                  value={latitude}
                  onChange={(e) => setLatitude(e.target.value)}
                  aria-invalid={!!errors.latitude}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {errors.latitude && <p className="text-sm text-red-400">{t(errors.latitude)}</p>}
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">{t('经度 *')}</Label>
                <Input
                  data-testid="admin-site-longitude"
                  value={longitude}
                  onChange={(e) => setLongitude(e.target.value)}
                  aria-invalid={!!errors.longitude}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {errors.longitude && <p className="text-sm text-red-400">{t(errors.longitude)}</p>}
              </div>
            </div>
            
            <div className="space-y-2">
              <Label className="text-slate-300">{t('营业时间（可选）')}</Label>
              <Input
                data-testid="admin-site-operating-hours"
                value={operatingHours}
                onChange={(e) => setOperatingHours(e.target.value)}
                placeholder={t('例如：00:00-24:00')}
                aria-invalid={!!errors.operating_hours}
                className="bg-slate-800 border-slate-600 text-slate-200"
              />
              {errors.operating_hours && <p className="text-sm text-red-400">{t(errors.operating_hours)}</p>}
            </div>
          </div>

          <DialogFooter>
            <Button
              data-testid="admin-site-create-submit"
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={submitting}
            >
              {t('取消')}
            </Button>
            <Button
              type="button"
              onClick={handleCreate}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={submitting}
            >
              {submitting ? t('创建中...') : t('创建')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
