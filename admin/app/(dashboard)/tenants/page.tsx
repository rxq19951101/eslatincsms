'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useAuthStore } from '@/store/authStore';
import type { TenantProvisionResponse, TenantProvisionResult, TenantRecord } from '@/types';
import { Building2, Copy, Plus, Trash2 } from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import {
  apiErrorMessageKey,
  apiFieldErrors,
  fieldErrors,
  tenantProvisionSchema,
  TENANT_PROVISION_API_FIELD_MAPPING,
  type FieldErrors,
} from '@/lib/validation';
import { tenantProvisionPayload, tenantProvisionResult } from '@/lib/tenant-provision';

const fetcher = (url: string) => apiGet<TenantRecord[]>(url);

function generatePassword(length = 12) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
  const bytes = new Uint8Array(length);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  let out = '';
  for (let i = 0; i < length; i++) out += chars[bytes[i] % chars.length];
  return out;
}

export default function TenantsPage() {
  const { t } = useI18n();
  const { user } = useAuthStore();
  const isSuperAdmin = !!user?.is_super_admin;
  const [searchQuery, setSearchQuery] = useState('');
  const [open, setOpen] = useState(false);

  // 新租户表单
  const [tenantName, setTenantName] = useState('');
  const [tenantDomain, setTenantDomain] = useState('');
  const [plan, setPlan] = useState<'free' | 'pro' | 'enterprise'>('free');
  const [maxChargePoints, setMaxChargePoints] = useState<number>(10);
  const [maxUsers, setMaxUsers] = useState<number>(100);

  // 初始管理员账号（给租户登录用）
  const [adminUsername, setAdminUsername] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminFullName, setAdminFullName] = useState('');
  const [adminPassword, setAdminPassword] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<FieldErrors>({});
  const [createdResult, setCreatedResult] = useState<TenantProvisionResult | null>(null);

  const { data: tenants, error, isLoading, mutate } = useSWR<TenantRecord[]>(
    API_ENDPOINTS.TENANTS,
    fetcher,
    { refreshInterval: 30000 }
  );

  const filteredTenants = useMemo(() => {
    const list = tenants || [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return list;
    return list.filter((t) => {
      return (
        t.name.toLowerCase().includes(q) ||
        String(t.domain || '').toLowerCase().includes(q)
      );
    });
  }, [tenants, searchQuery]);

  const resetCreateForm = () => {
    setTenantName('');
    setTenantDomain('');
    setPlan('free');
    setMaxChargePoints(10);
    setMaxUsers(100);
    setAdminUsername('');
    setAdminEmail('');
    setAdminFullName('');
    setAdminPassword('');
    setFormError(null);
    setFormErrors({});
    setCreatedResult(null);
  };

  const handleOpen = () => {
    resetCreateForm();
    setOpen(true);
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      alert(t('已复制到剪贴板'));
    } catch {
      alert(t('复制失败，请手动复制'));
    }
  };

  const handleCreate = async () => {
    const password = adminPassword || generatePassword(12);
    const result = tenantProvisionSchema.safeParse({
      name: tenantName,
      domain: tenantDomain,
      subscription_plan: plan,
      max_charge_points: maxChargePoints,
      max_users: maxUsers,
      admin_username: adminUsername,
      admin_email: adminEmail,
      admin_full_name: adminFullName,
      admin_password: password,
    });
    if (!result.success) {
      setFormErrors(fieldErrors(result.error));
      setFormError(null);
      return;
    }

    setSubmitting(true);
    setFormError(null);
    setFormErrors({});
    setCreatedResult(null);

    try {
      const provisioned = await apiPost<TenantProvisionResponse>(
        API_ENDPOINTS.TENANTS_PROVISION,
        tenantProvisionPayload(result.data)
      );
      setCreatedResult(tenantProvisionResult(provisioned, password));
      mutate();
    } catch (e) {
      setFormErrors(apiFieldErrors(e, TENANT_PROVISION_API_FIELD_MAPPING));
      setFormError(t(apiErrorMessageKey(e, '创建失败')));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteTenant = async (tenantId: string) => {
    const ok = confirm(t('确定要删除该租户吗？此操作不可恢复。'));
    if (!ok) return;
    try {
      await apiDelete(API_ENDPOINTS.TENANT_DETAIL(tenantId));
      mutate();
      alert(t('已删除'));
    } catch (e) {
      alert(t(apiErrorMessageKey(e, '删除失败')));
    }
  };

  if (!isSuperAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('租户管理')}</h1>
          <p className="text-slate-400 mt-1">{t('管理系统租户（仅超级管理员）')}</p>
        </div>
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardContent className="pt-10 pb-10">
            <div className="text-slate-300">
              {t('当前账号不是超级管理员，无法创建/管理租户。')}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

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
          <h1 className="text-3xl font-bold text-white">{t('租户管理')}</h1>
          <p className="text-slate-400 mt-1">{t('管理系统租户（仅超级管理员）')}</p>
        </div>
        <Button
          onClick={handleOpen}
          className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
        >
          <Plus className="h-4 w-4 mr-2" />
          {t('添加租户')}
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader className="space-y-4">
          <CardTitle className="text-white">{t('租户列表')}</CardTitle>
          <div className="flex flex-col md:flex-row gap-3">
            <div className="flex-1">
              <Input
                placeholder={t('搜索租户名称 / 域名...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-700/50 border-slate-600 text-slate-200 placeholder:text-slate-500"
              />
            </div>
            <div className="text-sm text-slate-400 flex items-center">
              {t('共')} {filteredTenants.length} {t('个')}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredTenants.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('名称')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('域名')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('状态')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('套餐')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('桩数上限')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('用户上限')}</th>
                    <th className="text-right py-3 px-4 text-slate-400 font-medium">{t('操作')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTenants.map((tenant) => (
                    <tr key={tenant.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="py-3 px-4 text-white">{tenant.name}</td>
                      <td className="py-3 px-4 text-slate-300">{tenant.domain || '-'}</td>
                      <td className="py-3 px-4 text-slate-300">{tenant.status}</td>
                      <td className="py-3 px-4 text-slate-300">{tenant.subscription_plan}</td>
                      <td className="py-3 px-4 text-slate-300">{tenant.max_charge_points}</td>
                      <td className="py-3 px-4 text-slate-300">{tenant.max_users}</td>
                      <td className="py-3 px-4 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDeleteTenant(tenant.id)}
                          className="bg-slate-700/50 border-slate-600 text-red-300 hover:bg-slate-600"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          {t('删除')}
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
              <p className="text-slate-400">{t('暂无租户')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100">
          <DialogHeader>
            <DialogTitle className="text-white">{t('创建租户（注册/开通）')}</DialogTitle>
            <DialogDescription className="text-slate-400">
              {t('租户、首个管理员和成员关系将以单个事务创建。')}
            </DialogDescription>
          </DialogHeader>

          {createdResult ? (
            <div className="space-y-4">
              <div className="p-3 rounded-md bg-green-500/10 border border-green-500/20">
                <div className="text-green-300 font-medium">{t('创建成功')}</div>
                <div className="text-sm text-slate-300 mt-2">{createdResult.tenant.name}</div>
              </div>

              {createdResult.admin && createdResult.temporary_password && (
                <div className="p-3 rounded-md bg-slate-800/50 border border-slate-700">
                  <div className="text-slate-200 font-medium">{t('租户管理员账号')}</div>
                  <div className="text-sm text-slate-300 mt-2 space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <span>{t('用户名：')}<span className="font-mono">{createdResult.admin.username}</span></span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy(createdResult.admin!.username)}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      >
                        <Copy className="h-4 w-4 mr-2" />
                        {t('复制')}
                      </Button>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>{t('密码：')}<span className="font-mono">{createdResult.temporary_password}</span></span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy(createdResult.temporary_password!)}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      >
                        <Copy className="h-4 w-4 mr-2" />
                        {t('复制')}
                      </Button>
                    </div>
                    <div className="text-xs text-slate-400">
                      {t('请尽快让租户管理员登录后修改密码。')}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-5">
              {formError && (
                <div className="p-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-md">
                  {formError}
                </div>
              )}

              <div className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('租户名称 *')}</Label>
                    <Input
                      value={tenantName}
                      onChange={(e) => setTenantName(e.target.value)}
                      placeholder={t('例如：EsLatin Colombia')}
                      aria-invalid={!!formErrors.name}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                    {formErrors.name && <p className="text-sm text-red-400">{t(formErrors.name)}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('域名（可选）')}</Label>
                    <Input
                      value={tenantDomain}
                      onChange={(e) => setTenantDomain(e.target.value)}
                      placeholder={t('例如：tenant1.eslatin.com.co')}
                      aria-invalid={!!formErrors.domain}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                    {formErrors.domain && <p className="text-sm text-red-400">{t(formErrors.domain)}</p>}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('套餐')}</Label>
                    <Select value={plan} onValueChange={(value) => setPlan(value as typeof plan)}>
                      <SelectTrigger className="bg-slate-800 border-slate-600 text-slate-200">
                        <SelectValue placeholder={t('选择套餐')} />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-900 border-slate-700">
                        <SelectItem value="free">free</SelectItem>
                        <SelectItem value="pro">pro</SelectItem>
                        <SelectItem value="enterprise">enterprise</SelectItem>
                      </SelectContent>
                    </Select>
                    {formErrors.subscription_plan && <p className="text-sm text-red-400">{t(formErrors.subscription_plan)}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('桩数上限')}</Label>
                    <Input
                      type="number"
                      value={String(maxChargePoints)}
                      onChange={(e) => setMaxChargePoints(Number(e.target.value))}
                      aria-invalid={!!formErrors.max_charge_points}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                    {formErrors.max_charge_points && <p className="text-sm text-red-400">{t(formErrors.max_charge_points)}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('用户上限')}</Label>
                    <Input
                      type="number"
                      value={String(maxUsers)}
                      onChange={(e) => setMaxUsers(Number(e.target.value))}
                      aria-invalid={!!formErrors.max_users}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                    {formErrors.max_users && <p className="text-sm text-red-400">{t(formErrors.max_users)}</p>}
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-700 pt-4 space-y-3">
                <div>
                  <div className="text-slate-200 font-medium">{t('创建租户管理员账号')}</div>
                  <div className="text-xs text-slate-400">{t('租户、首个管理员和成员关系将以单个事务创建。')}</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300">{t('管理员用户名 *')}</Label>
                      <Input
                        value={adminUsername}
                        onChange={(e) => setAdminUsername(e.target.value)}
                        placeholder={t('例如：tenant_admin')}
                        aria-invalid={!!formErrors.admin_username}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                      {formErrors.admin_username && <p className="text-sm text-red-400">{t(formErrors.admin_username)}</p>}
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">{t('管理员邮箱 *')}</Label>
                      <Input
                        value={adminEmail}
                        onChange={(e) => setAdminEmail(e.target.value)}
                        placeholder={t('例如：admin@tenant.com')}
                        aria-invalid={!!formErrors.admin_email}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                      {formErrors.admin_email && <p className="text-sm text-red-400">{t(formErrors.admin_email)}</p>}
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">{t('姓名（可选）')}</Label>
                      <Input
                        value={adminFullName}
                        onChange={(e) => setAdminFullName(e.target.value)}
                        aria-invalid={!!formErrors.admin_full_name}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                      {formErrors.admin_full_name && <p className="text-sm text-red-400">{t(formErrors.admin_full_name)}</p>}
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">{t('初始密码（可选）')}</Label>
                      <div className="flex gap-2">
                        <Input
                          value={adminPassword}
                          onChange={(e) => setAdminPassword(e.target.value)}
                          placeholder={t('留空将自动生成')}
                          type="password"
                          aria-invalid={!!formErrors.admin_password}
                          className="bg-slate-800 border-slate-600 text-slate-200"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setAdminPassword(generatePassword(12))}
                          className="bg-slate-800 border-slate-600 text-slate-200"
                        >
                          {t('生成')}
                        </Button>
                      </div>
                      {formErrors.admin_password && <p className="text-sm text-red-400">{t(formErrors.admin_password)}</p>}
                    </div>
                  </div>
              </div>
            </div>
          )}

          <DialogFooter>
            {createdResult ? (
              <Button
                onClick={() => setOpen(false)}
                className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              >
                {t('完成')}
              </Button>
            ) : (
              <>
                <Button
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
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
