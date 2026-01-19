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
import AddressAutocomplete from '@/components/sites/AddressAutocomplete';
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
import { ArrowLeft, Link2, Pencil, Plus, Save } from 'lucide-react';

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
  const params = useParams<{ id: string }>();
  const siteId = decodeURIComponent(String(params.id || ''));

  const { data: site, error, isLoading, mutate } = useSWR<SiteDetail>(
    API_ENDPOINTS.SITE_DETAIL(siteId),
    fetcher,
    { refreshInterval: 30000 }
  );

  const { permissions } = usePermissions();
  const canEditSite = useMemo(() => hasPermission(permissions, 'sites.edit'), [permissions]);
  const canEditTariff = useMemo(() => hasPermission(permissions, 'tariffs.edit'), [permissions]);
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
  const [cpId, setCpId] = useState('');
  const [cpVendor, setCpVendor] = useState('');
  const [cpModel, setCpModel] = useState('');
  const [cpConnectorCount, setCpConnectorCount] = useState('1');
  const [cpConnectorType, setCpConnectorType] = useState('Type2');

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
      setSaveError('无权限编辑站点信息');
      return;
    }
    setSaveError(null);
    const lat = Number(editLat);
    const lng = Number(editLng);
    if (!editName.trim() || !editAddress.trim()) {
      setSaveError('站点名称/地址不能为空');
      return;
    }
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      setSaveError('请填写正确的经纬度');
      return;
    }
    setSaving(true);
    try {
      await apiPut(API_ENDPOINTS.SITE_DETAIL(site.id), {
        name: editName.trim(),
        address: editAddress.trim(),
        latitude: lat,
        longitude: lng,
        operating_hours: editHours.trim() || null,
      });
      mutate();
      alert('已保存');
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const onSavePricing = async () => {
    if (!site) return;
    if (!canEditTariff) {
      setPricingError('无权限编辑定价');
      return;
    }
    setPricingError(null);
    const price = Number(editPrice);
    if (!Number.isFinite(price) || price <= 0) {
      setPricingError('请填写正确的电价（>0）');
      return;
    }
    setPricingSaving(true);
    try {
      await apiPut(API_ENDPOINTS.SITE_PRICING(site.id), {
        base_price_per_kwh: price,
        service_fee: 0,
      });
      mutate();
      alert('站点定价已保存');
    } catch (e) {
      setPricingError(e instanceof Error ? e.message : '保存定价失败');
    } finally {
      setPricingSaving(false);
    }
  };

  const mapCenter = useMemo(() => {
    // 优先使用编辑表单中的坐标
    const lat = Number(editLat);
    const lng = Number(editLng);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return { lat, lng };
    }
    // fallback：用站点原始坐标
    if (site && Number.isFinite(site.latitude) && Number.isFinite(site.longitude)) {
      return { lat: site.latitude, lng: site.longitude };
    }
    // 如果都没有，返回默认坐标（波哥大）
    return { lat: 4.6097, lng: -74.0817 };
  }, [editLat, editLng, site]);

  const openBindDialog = async () => {
    if (!site) return;
    if (!canEditAny) {
      alert('无权限执行绑定操作');
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
      setBindError(e instanceof Error ? e.message : '加载可绑定充电桩失败');
    } finally {
      setBindLoading(false);
    }
  };

  const onBind = async () => {
    if (!site) return;
    if (selectedIds.length === 0) {
      setBindError('请至少选择一个充电桩');
      return;
    }
    setBindError(null);
    setBindLoading(true);
    try {
      const body: BindChargePointsRequest = { charge_point_ids: selectedIds, force_move: true };
      await apiPost(API_ENDPOINTS.SITE_BIND_CHARGE_POINTS(site.id), body);
      setBindOpen(false);
      mutate();
      alert('绑定/迁移成功');
    } catch (e) {
      setBindError(e instanceof Error ? e.message : '绑定失败');
    } finally {
      setBindLoading(false);
    }
  };

  const openCreateDialog = () => {
    if (!canEditAny) {
      alert('无权限添加充电桩');
      return;
    }
    setCreateError(null);
    setCpId('');
    setCpVendor('');
    setCpModel('');
    setCpConnectorCount('1');
    setCpConnectorType('Type2');
    setCreateOpen(true);
  };

  const onCreateChargePoint = async () => {
    if (!site) return;
    const id = cpId.trim();
    if (!id) {
      setCreateError('请填写充电桩硬件码（charge_point_id）');
      return;
    }
    const count = Number(cpConnectorCount);
    if (!Number.isFinite(count) || count < 1 || count > 16) {
      setCreateError('枪口数量需为 1-16 的整数');
      return;
    }

    setCreateError(null);
    setCreateLoading(true);
    try {
      const body: CreateChargePointInSiteRequest = {
        id,
        vendor: cpVendor.trim() || undefined,
        model: cpModel.trim() || undefined,
        connector_count: count,
        connector_type: cpConnectorType,
      };
      await apiPost(API_ENDPOINTS.SITE_CREATE_CHARGE_POINT(site.id), body);
      setCreateOpen(false);
      mutate();
      alert('充电桩已添加并绑定到站点');
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : '创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">加载中...</div>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">加载失败，请刷新页面重试</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push('/sites')}
            className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            返回
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-white">{site.name}</h1>
            <p className="text-slate-400 mt-1 font-mono text-xs">{site.id}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setIsEditing((v) => !v)}
            disabled={!canEditAny}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
            title={!canEditAny ? '无权限编辑' : undefined}
          >
            <Pencil className="h-4 w-4 mr-2" />
            {isEditing ? '退出编辑' : '编辑'}
          </Button>
          <Button
            onClick={openCreateDialog}
            disabled={!canEditAny}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <Plus className="h-4 w-4 mr-2" />
            添加充电桩
          </Button>
          <Button
            onClick={openBindDialog}
            disabled={!canEditAny}
            className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
          >
            <Link2 className="h-4 w-4 mr-2" />
            绑定充电桩
          </Button>
          <Button
            onClick={onSave}
            disabled={saving || !isEditing || !canEditSite}
            className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
          >
            <Save className="h-4 w-4 mr-2" />
            {saving ? '保存中...' : '保存站点信息'}
          </Button>
        </div>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">站点信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {saveError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {saveError}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-slate-300">站点名称</Label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">营业时间</Label>
              <Input
                value={editHours}
                onChange={(e) => setEditHours(e.target.value)}
                placeholder="例如：00:00-24:00"
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-slate-300">地址</Label>
              <AddressAutocomplete
                value={editAddress}
                onChange={setEditAddress}
                onSelect={(s) => {
                  setEditAddress(s.display_name);
                  setEditLat(String(s.lat));
                  setEditLng(String(s.lon));
                }}
                placeholder="输入地址后选择建议，将自动填充经纬度"
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">纬度</Label>
              <Input
                value={editLat}
                onChange={(e) => setEditLat(e.target.value)}
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">经度</Label>
              <Input
                value={editLng}
                onChange={(e) => setEditLng(e.target.value)}
                disabled={!isEditing || !canEditSite}
                className="bg-slate-700/50 border-slate-600 text-slate-200"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label className="text-slate-300">站点定价（每kWh）</Label>
              <div className="flex gap-2">
                <Input
                  value={editPrice}
                  onChange={(e) => setEditPrice(e.target.value)}
                  placeholder={site.price_per_kwh != null ? String(site.price_per_kwh) : '未设置'}
                  disabled={!isEditing || !canEditTariff}
                  className="bg-slate-700/50 border-slate-600 text-slate-200"
                />
                <Button
                  onClick={onSavePricing}
                  disabled={!isEditing || !canEditTariff || pricingSaving}
                  className="bg-slate-700/50 border border-slate-600 text-slate-200 hover:bg-slate-600"
                >
                  {pricingSaving ? '保存中...' : '保存定价'}
                </Button>
              </div>
              {!!pricingError && <div className="text-sm text-red-300">{pricingError}</div>}
            </div>
          </div>
          <div className="text-sm text-slate-400">当前生效电价：{site.price_per_kwh != null ? site.price_per_kwh : '未设置'}</div>
        </CardContent>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">地图</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-400">
            {isEditing && canEditSite
              ? '点击地图可自动填充经纬度（lat/lng），用于站点定位。'
              : '地图展示站点位置，点击"编辑"按钮后可修改位置。'}
          </div>
          <GoogleMapView
            height="320px"
            zoom={15}
            center={mapCenter}
            markers={
              mapCenter
                ? [
                    {
                      lat: mapCenter.lat,
                      lng: mapCenter.lng,
                      title: site?.name || '站点',
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
          <CardTitle className="text-white">站点下充电桩（{site.charge_points.length}）</CardTitle>
        </CardHeader>
        <CardContent>
          {site.charge_points.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">充电桩ID</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">厂商/型号</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">状态</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">最后在线</th>
                    <th className="text-right py-3 px-4 text-slate-400 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {site.charge_points.map((cp) => (
                    <tr key={cp.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="py-3 px-4">
                        <button
                          onClick={() => router.push(`/chargers/${encodeURIComponent(cp.id)}`)}
                          className="text-white font-mono text-sm hover:text-purple-400 hover:underline transition-colors cursor-pointer"
                          title="点击查看详情"
                        >
                          {cp.id}
                        </button>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {(cp.vendor || 'Unknown') + ' ' + (cp.model || '')}
                      </td>
                      <td className="py-3 px-4">
                        <Badge className={getStatusColor(cp.status)}>{cp.status}</Badge>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {cp.last_seen ? new Date(cp.last_seen).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-end gap-2 flex-wrap">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => router.push(`/chargers/${encodeURIComponent(cp.id)}`)}
                            className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white border-0"
                          >
                            查看详情
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
                              覆盖定价
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
            <div className="text-slate-400">暂无充电桩，请先绑定。</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">设置充电桩覆盖定价</DialogTitle>
            <DialogDescription className="text-slate-400">
              桩级覆盖价优先于站点默认价（用于少数桩特殊价格）。
            </DialogDescription>
          </DialogHeader>

          {!!overrideError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {overrideError}
            </div>
          )}

          <div className="space-y-2">
            <Label className="text-slate-300">充电桩ID</Label>
            <div className="text-slate-200 font-mono text-sm">{overrideCpId || '-'}</div>
          </div>
          <div className="space-y-2">
            <Label className="text-slate-300">覆盖电价（每kWh）</Label>
            <Input
              value={overridePrice}
              onChange={(e) => setOverridePrice(e.target.value)}
              placeholder="例如：1.50"
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
              取消
            </Button>
            <Button
              type="button"
              onClick={async () => {
                if (!overrideCpId) return;
                if (!canEditTariff) {
                  setOverrideError('无权限编辑定价');
                  return;
                }
                const price = Number(overridePrice);
                if (!Number.isFinite(price) || price <= 0) {
                  setOverrideError('请填写正确的电价（>0）');
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
                  alert('覆盖定价已保存');
                } catch (e) {
                  setOverrideError(e instanceof Error ? e.message : '保存失败');
                } finally {
                  setOverrideSaving(false);
                }
              }}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={!canEditTariff || overrideSaving || !overrideCpId}
            >
              {overrideSaving ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={bindOpen} onOpenChange={setBindOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-white">绑定充电桩到站点</DialogTitle>
            <DialogDescription className="text-slate-400">
              从“可绑定”列表中选择充电桩，系统将迁移到当前站点（force_move=true）。
            </DialogDescription>
          </DialogHeader>

          {bindError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {bindError}
            </div>
          )}

          {bindLoading ? (
            <div className="text-slate-400">加载中...</div>
          ) : bindCandidates.length > 0 ? (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto border border-slate-800 rounded-md">
              <table className="w-full">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="border-b border-slate-800">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">选择</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">充电桩ID</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">当前站点</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">状态</th>
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
                      <td className="py-3 px-4 text-slate-200 font-mono text-sm">{cp.id}</td>
                      <td className="py-3 px-4 text-slate-300">
                        {cp.site_name ? `${cp.site_name} (${cp.site_id})` : cp.site_id}
                      </td>
                      <td className="py-3 px-4">
                        <Badge className={getStatusColor(cp.status)}>{cp.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-slate-400">
              当前没有“可绑定”的充电桩（默认只展示属于系统自动单桩站点的设备）。
            </div>
          )}

          <DialogFooter>
            <div className="flex-1 text-sm text-slate-400">
              已选择 {selectedIds.length} 个
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setBindOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={bindLoading}
            >
              取消
            </Button>
            <Button
              type="button"
              onClick={onBind}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={bindLoading || selectedIds.length === 0}
            >
              {bindLoading ? '处理中...' : '绑定/迁移'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-white">在站点下添加充电桩</DialogTitle>
            <DialogDescription className="text-slate-400">
              输入充电桩硬件码（charge_point_id）进行预注册，并自动绑定到当前站点。
            </DialogDescription>
          </DialogHeader>

          {createError && (
            <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
              {createError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">硬件码（charge_point_id）*</Label>
              <Input
                value={cpId}
                onChange={(e) => setCpId(e.target.value)}
                placeholder="例如：635310462（只能字母数字）"
                className="bg-slate-800 border-slate-600 text-slate-200"
              />
              <div className="text-xs text-slate-400">
                该值必须与充电桩 WS 连接参数一致（严格模式下要求字母数字）。
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">厂商（可选）</Label>
                <Input
                  value={cpVendor}
                  onChange={(e) => setCpVendor(e.target.value)}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">型号（可选）</Label>
                <Input
                  value={cpModel}
                  onChange={(e) => setCpModel(e.target.value)}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">枪口数量（EVSE 数）</Label>
                <Input
                  value={cpConnectorCount}
                  onChange={(e) => setCpConnectorCount(e.target.value)}
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">连接器类型</Label>
                <Input
                  value={cpConnectorType}
                  onChange={(e) => setCpConnectorType(e.target.value)}
                  placeholder="Type2/GBT/CCS2..."
                  className="bg-slate-800 border-slate-600 text-slate-200"
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
              className="bg-slate-800 border-slate-600 text-slate-200"
              disabled={createLoading}
            >
              取消
            </Button>
            <Button
              type="button"
              onClick={onCreateChargePoint}
              className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              disabled={createLoading}
            >
              {createLoading ? '创建中...' : '创建并绑定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

