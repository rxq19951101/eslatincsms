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
import type { AdminUserRecord, MembershipRecord, TenantRecord } from '@/types';
import { Building2, Copy, Plus, Trash2 } from 'lucide-react';

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
  const [createTenantAdmin, setCreateTenantAdmin] = useState(true);
  const [adminUsername, setAdminUsername] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminFullName, setAdminFullName] = useState('');
  const [adminPassword, setAdminPassword] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [createdResult, setCreatedResult] = useState<{
    tenant: TenantRecord;
    admin?: AdminUserRecord;
    password?: string;
  } | null>(null);

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
        t.id.toLowerCase().includes(q) ||
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
    setCreateTenantAdmin(true);
    setAdminUsername('');
    setAdminEmail('');
    setAdminFullName('');
    setAdminPassword('');
    setFormError(null);
    setCreatedResult(null);
  };

  const handleOpen = () => {
    resetCreateForm();
    setOpen(true);
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      alert('已复制到剪贴板');
    } catch {
      alert('复制失败，请手动复制');
    }
  };

  const handleCreate = async () => {
    if (!tenantName.trim()) {
      setFormError('请填写租户名称');
      return;
    }
    if (createTenantAdmin) {
      if (!adminUsername.trim()) {
        setFormError('请填写租户管理员用户名');
        return;
      }
      if (!adminEmail.trim()) {
        setFormError('请填写租户管理员邮箱');
        return;
      }
    }

    setSubmitting(true);
    setFormError(null);
    setCreatedResult(null);

    try {
      // 1) 创建租户
      const tenant = await apiPost<TenantRecord>(API_ENDPOINTS.TENANTS, {
        name: tenantName.trim(),
        domain: tenantDomain.trim() || null,
        subscription_plan: plan,
        max_charge_points: Number(maxChargePoints) || 10,
        max_users: Number(maxUsers) || 100,
        settings: {},
      });

      // 2) （可选）创建租户管理员账号，并绑定到该租户（membership）
      let createdAdmin: AdminUserRecord | undefined;
      let pwd: string | undefined;
      if (createTenantAdmin) {
        pwd = adminPassword.trim() || generatePassword(12);
        createdAdmin = await apiPost<AdminUserRecord>(API_ENDPOINTS.ADMIN_USERS, {
          username: adminUsername.trim(),
          email: adminEmail.trim(),
          password: pwd,
          full_name: adminFullName.trim() || null,
          is_super_admin: false,
        });

        // memberships 接口依赖 tenant_id_context，所以这里显式带上 X-Tenant-Id
        await apiPost<MembershipRecord>(
          API_ENDPOINTS.MEMBERSHIPS,
          { admin_user_id: createdAdmin.id, is_primary: true },
          { headers: { 'X-Tenant-Id': tenant.id } }
        );
      }

      setCreatedResult({ tenant, admin: createdAdmin, password: pwd });
      mutate();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteTenant = async (tenantId: string) => {
    const ok = confirm('确定要删除该租户吗？此操作不可恢复。');
    if (!ok) return;
    try {
      await apiDelete(API_ENDPOINTS.TENANT_DETAIL(tenantId));
      mutate();
      alert('已删除');
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  };

  if (!isSuperAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-white">租户管理</h1>
          <p className="text-slate-400 mt-1">管理系统租户（仅超级管理员）</p>
        </div>
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardContent className="pt-10 pb-10">
            <div className="text-slate-300">
              当前账号不是超级管理员，无法创建/管理租户。
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">加载失败，请刷新页面重试</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">租户管理</h1>
          <p className="text-slate-400 mt-1">管理系统租户（仅超级管理员）</p>
        </div>
        <Button
          onClick={handleOpen}
          className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
        >
          <Plus className="h-4 w-4 mr-2" />
          添加租户
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader className="space-y-4">
          <CardTitle className="text-white">租户列表</CardTitle>
          <div className="flex flex-col md:flex-row gap-3">
            <div className="flex-1">
              <Input
                placeholder="搜索租户 ID / 名称 / 域名..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-700/50 border-slate-600 text-slate-200 placeholder:text-slate-500"
              />
            </div>
            <div className="text-sm text-slate-400 flex items-center">
              共 {filteredTenants.length} 个
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredTenants.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">租户 ID</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">名称</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">域名</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">状态</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">套餐</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">桩数上限</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">用户上限</th>
                    <th className="text-right py-3 px-4 text-slate-400 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTenants.map((t) => (
                    <tr key={t.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="py-3 px-4 text-slate-300 font-mono text-xs">{t.id}</td>
                      <td className="py-3 px-4 text-white">{t.name}</td>
                      <td className="py-3 px-4 text-slate-300">{t.domain || '-'}</td>
                      <td className="py-3 px-4 text-slate-300">{t.status}</td>
                      <td className="py-3 px-4 text-slate-300">{t.subscription_plan}</td>
                      <td className="py-3 px-4 text-slate-300">{t.max_charge_points}</td>
                      <td className="py-3 px-4 text-slate-300">{t.max_users}</td>
                      <td className="py-3 px-4 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDeleteTenant(t.id)}
                          className="bg-slate-700/50 border-slate-600 text-red-300 hover:bg-slate-600"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          删除
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
              <p className="text-slate-400">暂无租户</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100">
          <DialogHeader>
            <DialogTitle className="text-white">创建租户（注册/开通）</DialogTitle>
            <DialogDescription className="text-slate-400">
              创建租户后可选自动创建一个“租户管理员账号”，用于该租户登录运营后台。
            </DialogDescription>
          </DialogHeader>

          {createdResult ? (
            <div className="space-y-4">
              <div className="p-3 rounded-md bg-green-500/10 border border-green-500/20">
                <div className="text-green-300 font-medium">创建成功</div>
                <div className="text-sm text-slate-300 mt-2">
                  <div className="flex items-center justify-between gap-3">
                    <span>租户 ID：<span className="font-mono">{createdResult.tenant.id}</span></span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCopy(createdResult.tenant.id)}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    >
                      <Copy className="h-4 w-4 mr-2" />
                      复制
                    </Button>
                  </div>
                </div>
              </div>

              {createdResult.admin && createdResult.password ? (
                <div className="p-3 rounded-md bg-slate-800/50 border border-slate-700">
                  <div className="text-slate-200 font-medium">租户管理员账号</div>
                  <div className="text-sm text-slate-300 mt-2 space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <span>用户名：<span className="font-mono">{createdResult.admin.username}</span></span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy(createdResult.admin!.username)}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      >
                        <Copy className="h-4 w-4 mr-2" />
                        复制
                      </Button>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>密码：<span className="font-mono">{createdResult.password}</span></span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopy(createdResult.password!)}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      >
                        <Copy className="h-4 w-4 mr-2" />
                        复制
                      </Button>
                    </div>
                    <div className="text-xs text-slate-400">
                      请尽快让租户管理员登录后修改密码。
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-300">
                  已创建租户（未创建租户管理员账号）。
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
                    <Label className="text-slate-300">租户名称 *</Label>
                    <Input
                      value={tenantName}
                      onChange={(e) => setTenantName(e.target.value)}
                      placeholder="例如：EsLatin Colombia"
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">域名（可选）</Label>
                    <Input
                      value={tenantDomain}
                      onChange={(e) => setTenantDomain(e.target.value)}
                      placeholder="例如：tenant1.eslatin.com"
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">套餐</Label>
                    <Select value={plan} onValueChange={(v) => setPlan(v as any)}>
                      <SelectTrigger className="bg-slate-800 border-slate-600 text-slate-200">
                        <SelectValue placeholder="选择套餐" />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-900 border-slate-700">
                        <SelectItem value="free">free</SelectItem>
                        <SelectItem value="pro">pro</SelectItem>
                        <SelectItem value="enterprise">enterprise</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">桩数上限</Label>
                    <Input
                      type="number"
                      value={String(maxChargePoints)}
                      onChange={(e) => setMaxChargePoints(Number(e.target.value))}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">用户上限</Label>
                    <Input
                      type="number"
                      value={String(maxUsers)}
                      onChange={(e) => setMaxUsers(Number(e.target.value))}
                      className="bg-slate-800 border-slate-600 text-slate-200"
                    />
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-700 pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-slate-200 font-medium">创建租户管理员账号</div>
                    <div className="text-xs text-slate-400">用于该租户登录后台（建议开启）。</div>
                  </div>
                  <Button
                    type="button"
                    variant={createTenantAdmin ? 'default' : 'outline'}
                    onClick={() => setCreateTenantAdmin((v) => !v)}
                    className={createTenantAdmin ? 'bg-purple-600 hover:bg-purple-700' : 'bg-slate-800 border-slate-600 text-slate-200'}
                  >
                    {createTenantAdmin ? '已开启' : '已关闭'}
                  </Button>
                </div>

                {createTenantAdmin && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300">管理员用户名 *</Label>
                      <Input
                        value={adminUsername}
                        onChange={(e) => setAdminUsername(e.target.value)}
                        placeholder="例如：tenant_admin"
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">管理员邮箱 *</Label>
                      <Input
                        value={adminEmail}
                        onChange={(e) => setAdminEmail(e.target.value)}
                        placeholder="例如：admin@tenant.com"
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">姓名（可选）</Label>
                      <Input
                        value={adminFullName}
                        onChange={(e) => setAdminFullName(e.target.value)}
                        className="bg-slate-800 border-slate-600 text-slate-200"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">初始密码（可选）</Label>
                      <div className="flex gap-2">
                        <Input
                          value={adminPassword}
                          onChange={(e) => setAdminPassword(e.target.value)}
                          placeholder="留空将自动生成"
                          className="bg-slate-800 border-slate-600 text-slate-200"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setAdminPassword(generatePassword(12))}
                          className="bg-slate-800 border-slate-600 text-slate-200"
                        >
                          生成
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            {createdResult ? (
              <Button
                onClick={() => setOpen(false)}
                className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              >
                完成
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
                  取消
                </Button>
                <Button
                  type="button"
                  onClick={handleCreate}
                  className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                  disabled={submitting}
                >
                  {submitting ? '创建中...' : '创建'}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}