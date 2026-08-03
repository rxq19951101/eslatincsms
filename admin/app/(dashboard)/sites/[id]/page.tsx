'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { useParams, useRouter } from 'next/navigation';
import { apiGet, apiPost, apiPut } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import type { BindChargePointsRequest, CreateChargePointInSiteRequest, SiteDetail, SiteDetailChargePoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import AddressAutocomplete from '@/components/sites/AddressAutocomplete';
import SiteLifecyclePanel, { SiteArchiveBlocker } from '@/components/sites/SiteLifecyclePanel';
import GoogleMapView from '@/components/map/GoogleMapView';
import { hasPermission, usePermissions } from '@/hooks/usePermissions';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Copy, Link2, Pencil, Plus, Save, Trash2 } from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { formatDateTime } from '@/lib/localization';
import {
  chargePointSchema,
  apiErrorMessageKey,
  apiFieldErrors,
  fieldErrors,
  priceSchema,
  siteSchema,
  SITE_API_FIELD_MAPPING,
  type FieldErrors,
} from '@/lib/validation';

const fetcher = (url: string) => apiGet<SiteDetail>(url);

function getStatusColor(status: string) {
  switch ((status || '').toLowerCase()) {
    case 'available':
      return 'bg-green-500/20 text-green-400 border-green-500/50';
    case 'charging':
      return 'bg-blue-500/20 text-blue-400 border-blue-500/50';
    case 'faulted':
      return 'bg-red-500/20 text-red-400 border-red-500/50';
    case 'unavailable':
      return 'bg-gray-500/20 text-gray-400 border-gray-500/50';
    default:
      return 'bg-slate-500/20 text-slate-400 border-slate-500/50';
  }
}

export default function SiteDetailPage() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const params = useParams<{ id: string }>();
  const siteId = decodeURIComponent(String(params.id || ''));

  const { data: site, error, isLoading, mutate } = useSWR<SiteDetail>(
    API_ENDPOINTS.SITE_DETAIL(siteId),
    fetcher,
    { refreshInterval: 30000 }
  );
  const isArchived = site?.lifecycle_status === 'archived';

  const { permissions } = usePermissions();
  const canWriteSites = useMemo(() => hasPermission(permissions, 'sites.write'), [permissions]);
  const canEditSite = canWriteSites && !isArchived;
  const canEditTariff = useMemo(
    () => hasPermission(permissions, 'tariffs.edit') && !isArchived,
    [permissions, isArchived]
  );
  const canEditAny = canEditSite || canEditTariff;

  const [isEditing, setIsEditing] = useState(false);

  // 编辑表单（懒初始化）
  const [initialized, setInitialized] = useState(false);
  const [editName, setEditName] = useState('');
  const [editAddress, setEditAddress] = useState('');
  const [editLat, setEditLat] = useState('');
  const [editLng, setEditLng] = useState('');
  const [editHours, setEditHours] = useState('');
  const [editPrice, setEditPrice] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [siteErrors, setSiteErrors] = useState<FieldErrors>({});
  const [pricingSaving, setPricingSaving] = useState(false);
  const [pricingError, setPricingError] = useState<string | null>(null);

  // 绑定弹窗
  const [bindOpen, setBindOpen] = useState(false);
  const [bindLoading, setBindLoading] = useState(false);
  const [bindError, setBindError] = useState<string | null>(null);
  const [bindCandidates, setBindCandidates] = useState<SiteDetailChargePoint[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const selectedIds = useMemo(() => Object.entries(selected).filter(([, v]) => v).map(([k]) => k), [selected]);

  // 站点内新增充电桩弹窗
  const [createOpen, setCreateOpen] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createErrors, setCreateErrors] = useState<FieldErrors>({});
  const [cpId, setCpId] = useState('');
  const [cpDisplayCode, setCpDisplayCode] = useState('A01');
  const [cpDisplayName, setCpDisplayName] = useState('');
  const [cpLocationHint, setCpLocationHint] = useState('');
  const [cpVendor, setCpVendor] = useState('');
  const [cpModel, setCpModel] = useState('');
  const [cpEvses, setCpEvses] = useState([
    { evse_id: 1, physical_reference: 'A01-1', connector_type: 'Type2', max_power_kw: '7' },
  ]);
  const [provisionedCredentials, setProvisionedCredentials] = useState<null | {
    username: string; secret: string; query_url: string; path_url: string;
  }>(null);

  // 覆盖价弹窗（桩级）
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideCpId, setOverrideCpId] = useState<string | null>(null);
  const [overridePrice, setOverridePrice] = useState<string>('');
  const [overrideSaving, setOverrideSaving] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  // 初始化编辑表单（仅一次，避免覆盖用户输入）
  useEffect(() => {
    if (!site || initialized) return;
    setEditName(site.name);
    setEditAddress(site.address);
    setEditLat(String(site.latitude));
    setEditLng(String(site.longitude));
    setEditHours(site.operating_hours || '');
    setEditPrice(site.price_per_kwh != null ? String(site.price_per_kwh) : '');
    setInitialized(true);
  }, [site, initialized]);

  const onSave = async () => {
    if (!site) return;
    if (!canEditSite) {
      setSaveError(t('无权限编辑站点信息'));
      return;
    }
    setSaveError(null);
    const result = siteSchema.safeParse({
      name: editName,
      address: editAddress,
      latitude: editLat,
      longitude: editLng,
      operating_hours: editHours,
    });
    if (!result.success) {
      setSiteErrors(fieldErrors(result.error));
      return;
    }
    setSiteErrors({});
    setSaving(true);
    try {
      await apiPut(API_ENDPOINTS.SITE_DETAIL(site.id), {
        ...result.data,
        operating_hours: result.data.operating_hours || null,
      });
      mutate();
      alert(t('已保存'));
    } catch (e) {
      setSiteErrors(apiFieldErrors(e, SITE_API_FIELD_MAPPING));
      setSaveError(t(apiErrorMessageKey(e, '保存失败')));
    } finally {
      setSaving(false);
    }
  };

  const onSavePricing = async () => {
    if (!site) return;
    if (!canEditTariff) {
      setPricingError(t('无权限编辑定价'));
      return;
    }
    setPricingError(null);
    const result = priceSchema.safeParse({ price: editPrice });
    if (!result.success) {
      setPricingError(t(result.error.issues[0].message));
      return;
    }
    setPricingSaving(true);
    try {
      await apiPut(API_ENDPOINTS.SITE_PRICING(site.id), {
        base_price_per_kwh: result.data.price,
        service_fee: 0,
      });
      mutate();
      alert(t('站点定价已保存'));
    } catch (e) {
      setPricingError(t(apiErrorMessageKey(e, '保存定价失败')));
    } finally {
      setPricingSaving(false);
    }
  };

  const hasConfiguredCoordinates = useMemo(() => {
    const lat = Number(editLat);
    const lng = Number(editLng);
    return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 && !(lat === 0 && lng === 0);
  }, [editLat, editLng]);

  const mapCenter = useMemo(() => {
    // 优先使用编辑表单中的坐标
    const lat = Number(editLat);
    const lng = Number(editLng);
    if (hasConfiguredCoordinates) {
      return { lat, lng };
    }
    // fallback：用站点原始坐标
    if (site && Number.isFinite(site.latitude) && Number.isFinite(site.longitude) && !(site.latitude === 0 && site.longitude === 0)) {
      return { lat: site.latitude, lng: site.longitude };
    }
    // 如果都没有，返回默认坐标（波哥大）
    return { lat: 4.6097, lng: -74.0817 };
  }, [editLat, editLng, site, hasConfiguredCoordinates]);

  const openBindDialog = async () => {
    if (!site) return;
    if (!canEditSite) {
      alert(t('无权限执行绑定操作'));
      return;
    }
    setBindOpen(true);
    setBindLoading(true);
    setBindError(null);
    setBindCandidates([]);
    setSelected({});
    try {
      const candidates = await apiGet<SiteDetailChargePoint[]>(API_ENDPOINTS.SITE_BINDABLE_CHARGE_POINTS(site.id));
      setBindCandidates(candidates);
    } catch (e) {
      setBindError(t(apiErrorMessageKey(e, '加载可绑定充电桩失败')));
    } finally {
      setBindLoading(false);
    }
  };

  const onBind = async () => {
    if (!site) return;
    if (selectedIds.length === 0) {
      setBindError(t('请至少选择一个充电桩'));
      return;
    }
    setBindError(null);
    setBindLoading(true);
    try {
      const body: BindChargePointsRequest = { charge_point_ids: selectedIds, force_move: true };
      await apiPost(API_ENDPOINTS.SITE_BIND_CHARGE_POINTS(site.id), body);
      setBindOpen(false);
      mutate();
      alert(t('绑定/迁移成功'));
    } catch (e) {
      setBindError(t(apiErrorMessageKey(e, '绑定失败')));
    } finally {
      setBindLoading(false);
    }
  };

  const openCreateDialog = () => {
    if (!canEditSite) {
      alert(t('无权限添加充电桩'));
      return;
    }
    setCreateError(null);
    setCreateErrors({});
    setCpId('');
    setCpDisplayCode('A01');
    setCpDisplayName('');
    setCpLocationHint('');
    setCpVendor('');
    setCpModel('');
    setCpEvses([{ evse_id: 1, physical_reference: 'A01-1', connector_type: 'Type2', max_power_kw: '7' }]);
    setCreateOpen(true);
  };

  const openLifecycleBlocker = (blocker: SiteArchiveBlocker) => {
    if (blocker.type === 'active_charge_point') {
      router.push(`/chargers/${encodeURIComponent(blocker.resource_id)}`);
      return;
    }
    if (blocker.type === 'ongoing_session') {
      router.push('/sessions');
      return;
    }
    router.push('/transactions');
  };

  const onCreateChargePoint = async () => {
    if (!site) return;
    const result = chargePointSchema.safeParse({
      id: cpId,
      display_code: cpDisplayCode,
      display_name: cpDisplayName,
      location_hint: cpLocationHint,
      vendor: cpVendor,
      model: cpModel,
      connector_count: cpEvses.length,
      connector_type: cpEvses[0]?.connector_type || 'Type2',
      evses: cpEvses,
    });
    if (!result.success) {
      setCreateErrors(fieldErrors(result.error));
      return;
    }

    setCreateError(null);
    setCreateErrors({});
    setCreateLoading(true);
    try {
      const body: CreateChargePointInSiteRequest = {
        ...result.data,
        display_name: result.data.display_name || undefined,
        location_hint: result.data.location_hint || undefined,
        vendor: result.data.vendor || undefined,
        model: result.data.model || undefined,
      };
      const created = await apiPost<{
        ocpp_credentials: { username: string; secret: string; query_url: string; path_url: string };
      }>(API_ENDPOINTS.SITE_CREATE_CHARGE_POINT(site.id), body);
      setCreateOpen(false);
      setProvisionedCredentials(created.ocpp_credentials);
      mutate();
      alert(t('充电桩已添加并绑定到站点'));
    } catch (e) {
      setCreateError(t(apiErrorMessageKey(e, '创建失败')));
    } finally {
      setCreateLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">{t('加载中...')}</div>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{t('加载失败，请刷新页面重试')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            data-testid="admin-charger-create-open"
            variant="outline"
            size="sm"
            onClick={() => router.push('/sites')}
            className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            {t('返回')}
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-white">{t(site.name)}</h1>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setIsEditing((v) => !v)}
            disabled={!canEditAny}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
            title={!canEditAny ? t('无权限编辑') : undefined}
          >
            <Pencil className="h-4 w-4 mr-2" />
            {isEditing ? t('退出编辑') : t('编辑')}
          </Button>
          <Button
            onClick={openCreateDialog}
            disabled={!canEditSite}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <Plus className="h-4 w-4 mr-2" />
            {t('添加充电桩')}
          </Button>
          <Button
            onClick={openBindDialog}
            disabled={!canEditSite}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <Link2 className="h-4 w-4 mr-2" />
            {t('绑定充电桩')}
          </Button>
          <Button
            onClick={onSave}
            disabled={saving || !isEditing || !canEditSite}
            className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
          >
            <Save className="h-4 w-4 mr-2" />
            {saving ? t('保存中...') : t('保存站点信息')}
          </Button>
        </div>
      </div>

      <SiteLifecyclePanel
        site={site}
        canWrite={canWriteSites}
        onChanged={() => mutate()}
        onDeleted={() => router.push('/sites')}
        onOpenBlocker={openLifecycleBlocker}
      />

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('站点信息')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {saveError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {saveError}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-slate-300">{t('站点名称')}</Label>
              <Input
                value={!isEditing ? t(editName) : editName}
                onChange={(e) => setEditName(e.target.value)}
                disabled={!isEditing || !canEditSite}
                aria-invalid={!!siteErrors.name}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
              {siteErrors.name && <p className="text-sm text-red-400">{t(siteErrors.name)}</p>}
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">{t('营业时间')}</Label>
              <Input
                value={editHours}
                onChange={(e) => setEditHours(e.target.value)}
                placeholder={t('例如：00:00-24:00')}
                disabled={!isEditing || !canEditSite}
                aria-invalid={!!siteErrors.operating_hours}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
              {siteErrors.operating_hours && <p className="text-sm text-red-400">{t(siteErrors.operating_hours)}</p>}
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-slate-300">{t('地址')}</Label>
              <AddressAutocomplete
                value={!isEditing ? t(editAddress) : editAddress}
                onChange={setEditAddress}
                onSelect={(s) => {
                  setEditAddress(s.display_name);
                  setEditLat(String(s.lat));
                  setEditLng(String(s.lon));
                }}
                placeholder={t('输入地址后选择建议，将自动填充经纬度')}
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
              {siteErrors.address && <p className="text-sm text-red-400">{t(siteErrors.address)}</p>}
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">{t('纬度')}</Label>
              <Input
                value={editLat}
                onChange={(e) => setEditLat(e.target.value)}
                disabled={!isEditing || !canEditSite}
                aria-invalid={!!siteErrors.latitude}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
              {siteErrors.latitude && <p className="text-sm text-red-400">{t(siteErrors.latitude)}</p>}
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">{t('经度')}</Label>
              <Input
                value={editLng}
                onChange={(e) => setEditLng(e.target.value)}
                disabled={!isEditing || !canEditSite}
                aria-invalid={!!siteErrors.longitude}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
              {siteErrors.longitude && <p className="text-sm text-red-400">{t(siteErrors.longitude)}</p>}
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-slate-300">{t('站点定价（每kWh）')}</Label>
              <div className="flex gap-2">
                <Input
                  value={editPrice}
                  onChange={(e) => setEditPrice(e.target.value)}
                  placeholder={site.price_per_kwh != null ? String(site.price_per_kwh) : t('未设置')}
                  disabled={!isEditing || !canEditTariff}
                  className="bg-slate-700/50 border-slate-600 text-slate-200"
                />
                <Button
                  onClick={onSavePricing}
                  disabled={!isEditing || !canEditTariff || pricingSaving}
                  className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  {pricingSaving ? t('保存中...') : t('保存定价')}
                </Button>
              </div>
              {!!pricingError && <div className="text-sm text-red-300">{pricingError}</div>}
            </div>
          </div>
          <div className="text-sm text-slate-400">{t('当前生效电价：')}{site.price_per_kwh != null ? site.price_per_kwh : t('未设置')}</div>
        </CardContent>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('地图')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-400">
            {isEditing && canEditSite
              ? t('点击地图可自动填充经纬度（lat/lng），用于站点定位。')
              : t('地图展示站点位置，点击“编辑”按钮后可修改位置。')}
          </div>
          <GoogleMapView
            height="320px"
            zoom={15}
            center={mapCenter}
            markers={
              hasConfiguredCoordinates
                ? [
                    {
                      lat: mapCenter.lat,
                      lng: mapCenter.lng,
                      title: site?.name ? t(site.name) : t('站点'),
                    },
                  ]
                : []
            }
            onClick={
              isEditing && canEditSite
                ? (lat, lng) => {
                    setEditLat(String(lat));
                    setEditLng(String(lng));
                  }
                : undefined
            }
            disableInteraction={!isEditing || !canEditSite}
          />
        </CardContent>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('站点下充电桩')} ({site.charge_points.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {site.charge_points.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('公开编号')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('厂商/型号')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('状态')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('最后在线')}</th>
                    <th className="text-right py-3 px-4 text-slate-400 font-medium">{t('操作')}</th>
                  </tr>
                </thead>
                <tbody>
                  {site.charge_points.map((cp) => (
                    <tr key={cp.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="py-3 px-4">
                        <button
                          onClick={() => router.push(`/chargers/${encodeURIComponent(cp.ocpp_identity || cp.id)}`)}
                          className="text-white font-mono text-sm hover:text-purple-400 hover:underline transition-colors cursor-pointer"
                          title={t('点击查看详情')}
                        >
                          {cp.display_name || cp.display_code}
                        </button>
                        {cp.display_name && <div className="mt-1 text-xs text-slate-400">{cp.display_code}</div>}
                        {cp.location_hint && <div className="mt-1 text-xs text-slate-400">{cp.location_hint}</div>}
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {(cp.vendor || 'Unknown') + ' ' + (cp.model || '')}
                      </td>
                      <td className="py-3 px-4">
                        <Badge className={getStatusColor(cp.status)}>{cp.status}</Badge>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {formatDateTime(cp.last_seen, locale, t('common.notAvailable'))}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-end gap-2 flex-wrap">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => router.push(`/chargers/${encodeURIComponent(cp.ocpp_identity || cp.id)}`)}
                            className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white border-0"
                          >
                            {t('查看详情')}
                          </Button>
                          {isEditing && canEditTariff && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setOverrideCpId(cp.id);
                                setOverridePrice('');
                                setOverrideError(null);
                                setOverrideOpen(true);
                              }}
                              className="bg-slate-800 border-slate-600 text-slate-200 hover:bg-slate-600"
                            >
                              {t('覆盖定价')}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-slate-400">{t('暂无充电桩，请先绑定。')}</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">{t('设置充电桩覆盖定价')}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {t('桩级覆盖价优先于站点默认价（用于少数桩特殊价格）。')}
            </DialogDescription>
          </DialogHeader>

          {!!overrideError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {overrideError}
            </div>
          )}

          <div className="space-y-2">
            <Label className="text-slate-300">{t('覆盖电价（每kWh）')}</Label>
            <Input
              value={overridePrice}
              onChange={(e) => setOverridePrice(e.target.value)}
              placeholder={t('例如：1.50')}
              disabled={!canEditTariff || overrideSaving}
              className="bg-slate-800 border-slate-600 text-slate-200"
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOverrideOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={overrideSaving}
            >
              {t('取消')}
            </Button>
            <Button
              type="button"
              onClick={async () => {
                if (!overrideCpId) return;
                if (!canEditTariff) {
                  setOverrideError(t('无权限编辑定价'));
                  return;
                }
                const price = Number(overridePrice);
                if (!Number.isFinite(price) || price <= 0) {
                  setOverrideError(t('请填写正确的电价（>0）'));
                  return;
                }
                setOverrideError(null);
                setOverrideSaving(true);
                try {
                  await apiPut(API_ENDPOINTS.CHARGER_PRICING(overrideCpId), {
                    base_price_per_kwh: price,
                    service_fee: 0,
                  });
                  setOverrideOpen(false);
                  alert(t('覆盖定价已保存'));
                } catch (e) {
                  setOverrideError(t(apiErrorMessageKey(e, '保存失败')));
                } finally {
                  setOverrideSaving(false);
                }
              }}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={!canEditTariff || overrideSaving || !overrideCpId}
            >
              {overrideSaving ? t('保存中...') : t('保存')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={bindOpen} onOpenChange={setBindOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-white">{t('绑定充电桩到站点')}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {t('从“可绑定”列表中选择充电桩，系统将迁移到当前站点。')}
            </DialogDescription>
          </DialogHeader>

          {bindError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {bindError}
            </div>
          )}

          {bindLoading ? (
            <div className="text-slate-400">{t('加载中...')}</div>
          ) : bindCandidates.length > 0 ? (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto border border-slate-800 rounded-md">
              <table className="w-full">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="border-b border-slate-800">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('选择')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('OCPP 身份')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('当前站点')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('状态')}</th>
                  </tr>
                </thead>
                <tbody>
                  {bindCandidates.map((cp) => (
                    <tr key={cp.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-3 px-4">
                        <input
                          type="checkbox"
                          checked={!!selected[cp.id]}
                          onChange={(e) => setSelected((prev) => ({ ...prev, [cp.id]: e.target.checked }))}
                        />
                      </td>
                      <td className="py-3 px-4 text-slate-200 font-mono text-sm">{cp.ocpp_identity || t('未提供')}</td>
                      <td className="py-3 px-4 text-slate-300">
                        {cp.site_name ? t(cp.site_name) : t('未分配')}
                      </td>
                      <td className="py-3 px-4">
                        <Badge className={getStatusColor(cp.status)}>{t(cp.status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-slate-400">
              {t('当前没有可绑定的充电桩。')}
            </div>
          )}

          <DialogFooter>
            <div className="flex-1 text-sm text-slate-400">
              {t('已选择')} {selectedIds.length}
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setBindOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={bindLoading}
            >
              {t('取消')}
            </Button>
            <Button
              type="button"
              onClick={onBind}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={bindLoading || selectedIds.length === 0}
            >
              {bindLoading ? t('处理中...') : t('绑定/迁移')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent data-testid="admin-charger-create-dialog" className="bg-slate-900 border-slate-700 text-slate-100 max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-white">{t('在站点下添加充电桩')}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {t('输入充电桩硬件码进行预注册，并自动绑定到当前站点。')}
            </DialogDescription>
          </DialogHeader>

          {createError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {createError}
            </div>
          )}

          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">{t('公开编号 *')}</Label>
                <Input
                  data-testid="admin-charger-display-code"
                  value={cpDisplayCode}
                  onChange={(e) => {
                    const previousCode = cpDisplayCode.trim() || 'A01';
                    const nextCode = e.target.value.toUpperCase();
                    setCpDisplayCode(nextCode);
                    setCpEvses((current) => current.map((evse) => (
                      evse.physical_reference === `${previousCode}-${evse.evse_id}`
                        ? { ...evse, physical_reference: `${nextCode.trim() || 'A01'}-${evse.evse_id}` }
                        : evse
                    )));
                  }}
                  placeholder={t('例如：A01')}
                  aria-invalid={!!createErrors.display_code}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {createErrors.display_code && <p className="text-sm text-red-400">{t(createErrors.display_code)}</p>}
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">{t('公开名称（可选）')}</Label>
                <Input
                  data-testid="admin-charger-display-name"
                  value={cpDisplayName}
                  onChange={(e) => setCpDisplayName(e.target.value)}
                  aria-invalid={!!createErrors.display_name}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {createErrors.display_name && <p className="text-sm text-red-400">{t(createErrors.display_name)}</p>}
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">{t('位置提示（可选）')}</Label>
              <Input
                data-testid="admin-charger-location-hint"
                value={cpLocationHint}
                onChange={(e) => setCpLocationHint(e.target.value)}
                placeholder={t('例如：P2 / 42 号车位')}
                aria-invalid={!!createErrors.location_hint}
                className="bg-slate-800 border-slate-600 text-slate-200"
              />
              {createErrors.location_hint && <p className="text-sm text-red-400">{t(createErrors.location_hint)}</p>}
              <div className="text-xs text-slate-400">{t('司机在 App 和设备现场看到这些公开标签。')}</div>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">{t('充电桩硬件码 *')}</Label>
              <Input
                data-testid="admin-charger-ocpp-identity"
                value={cpId}
                onChange={(e) => setCpId(e.target.value)}
                placeholder={t('例如：CO.BOGOTA:CP-01')}
                aria-invalid={!!createErrors.id}
                className="bg-slate-800 border-slate-600 text-slate-200"
              />
              {createErrors.id && <p className="text-sm text-red-400">{t(createErrors.id)}</p>}
              <div className="text-xs text-slate-400">
                {t('该值必须与充电桩 WebSocket 连接参数一致。')}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">{t('厂商（可选）')}</Label>
                <Input
                  data-testid="admin-charger-vendor"
                  value={cpVendor}
                  onChange={(e) => setCpVendor(e.target.value)}
                  aria-invalid={!!createErrors.vendor}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {createErrors.vendor && <p className="text-sm text-red-400">{t(createErrors.vendor)}</p>}
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">{t('型号（可选）')}</Label>
                <Input
                  data-testid="admin-charger-model"
                  value={cpModel}
                  onChange={(e) => setCpModel(e.target.value)}
                  aria-invalid={!!createErrors.model}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
                {createErrors.model && <p className="text-sm text-red-400">{t(createErrors.model)}</p>}
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-slate-300">{t('EVSE / 枪口配置')}</Label>
                <Button type="button" variant="outline" size="sm" onClick={() => {
                  const next = cpEvses.length + 1;
                  setCpEvses([...cpEvses, { evse_id: next, physical_reference: `${cpDisplayCode.trim() || 'A01'}-${next}`, connector_type: 'Type2', max_power_kw: '7' }]);
                }} disabled={cpEvses.length >= 16}>
                  <Plus className="h-4 w-4" /> {t('添加枪口')}
                </Button>
              </div>
              {cpEvses.map((evse, index) => (
                <div key={index} className="grid grid-cols-1 md:grid-cols-[90px_1fr_1fr_120px_40px] gap-2 rounded-md border border-slate-700 p-3">
                  <Input aria-label={t('EVSE 编号')} type="number" min={1} max={16} value={evse.evse_id}
                    onChange={(e) => setCpEvses(cpEvses.map((item, i) => i === index ? { ...item, evse_id: Number(e.target.value) } : item))}
                    className="bg-slate-800 border-slate-600" />
                  <Input aria-label={t('物理编号')} value={evse.physical_reference} placeholder="A-01"
                    onChange={(e) => setCpEvses(cpEvses.map((item, i) => i === index ? { ...item, physical_reference: e.target.value } : item))}
                    className="bg-slate-800 border-slate-600" />
                  <Select
                    value={evse.connector_type}
                    onValueChange={(value) => setCpEvses(cpEvses.map((item, i) => i === index ? { ...item, connector_type: value } : item))}
                  >
                    <SelectTrigger aria-label={t('连接器类型')} className="bg-slate-800 border-slate-600">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['Type2', 'CCS1', 'CCS2', 'CHAdeMO', 'NACS', 'GB_T_AC', 'GB_T_DC'].map((value) => (
                        <SelectItem key={value} value={value}>{value}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input aria-label={t('最大功率 kW')} type="number" min="0.1" step="0.1" value={evse.max_power_kw}
                    onChange={(e) => setCpEvses(cpEvses.map((item, i) => i === index ? { ...item, max_power_kw: e.target.value } : item))}
                    className="bg-slate-800 border-slate-600" />
                  <Button type="button" variant="ghost" size="icon" aria-label={t('删除枪口')}
                    disabled={cpEvses.length === 1} onClick={() => setCpEvses(cpEvses.filter((_, i) => i !== index))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button
              data-testid="admin-charger-create-submit"
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={createLoading}
            >
              {t('取消')}
            </Button>
            <Button
              type="button"
              onClick={onCreateChargePoint}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={createLoading}
            >
              {createLoading ? t('创建中...') : t('创建并绑定')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!provisionedCredentials} onOpenChange={(open) => !open && setProvisionedCredentials(null)}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-xl">
          <DialogHeader>
            <DialogTitle>{t('保存充电桩接入凭据')}</DialogTitle>
            <DialogDescription>{t('密钥只显示这一次。请立即保存到设备安全配置中。')}</DialogDescription>
          </DialogHeader>
          {provisionedCredentials && (
            <div className="space-y-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-4 font-mono text-sm break-all">
              <div><span className="text-slate-400">Identity: </span>{provisionedCredentials.username}</div>
              <div><span className="text-slate-400">Secret: </span>{provisionedCredentials.secret}</div>
              <div><span className="text-slate-400">URL 1: </span>{provisionedCredentials.query_url}</div>
              <div><span className="text-slate-400">URL 2: </span>{provisionedCredentials.path_url}</div>
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => provisionedCredentials && navigator.clipboard.writeText(JSON.stringify(provisionedCredentials, null, 2))}>
              <Copy className="h-4 w-4" /> {t('复制凭据')}
            </Button>
            <Button type="button" onClick={() => setProvisionedCredentials(null)}>{t('我已安全保存')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
