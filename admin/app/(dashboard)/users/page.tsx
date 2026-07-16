'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Users, RefreshCw } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';

interface AdminUser {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  is_super_admin: boolean;
  last_login_at?: string;
  created_at: string;
}

interface EndUser {
  id: string;
  phone: string;
  email?: string;
  full_name?: string;
  id_tag: string;
  balance: number;
  status: string;
}

interface AppUser {
  id: string;
  email: string;
  phone?: string;
  full_name?: string;
  balance: number;
  status: string;
  has_unpaid_charges: boolean;
  email_verified: boolean;
  created_at?: string;
}

export default function UsersPage() {
  const [tab, setTab] = useState('appuser');
  const [adjustUserId, setAdjustUserId] = useState<string | null>(null);
  const [adjustAmount, setAdjustAmount] = useState('10000');
  const [adjustNote, setAdjustNote] = useState('');
  const [adjusting, setAdjusting] = useState(false);
  const [adjustError, setAdjustError] = useState<string | null>(null);

  const { data: adminUsers, mutate: refreshAdmin, isLoading: loadingAdmin } = useSWR<AdminUser[]>(
    tab === 'admin' ? API_ENDPOINTS.ADMIN_USERS : null,
    (url) => apiGet<AdminUser[]>(url)
  );

  const { data: endUsers, mutate: refreshEnd, isLoading: loadingEnd } = useSWR<EndUser[]>(
    tab === 'enduser' ? API_ENDPOINTS.END_USERS : null,
    (url) => apiGet<EndUser[]>(url)
  );

  const { data: appUsers, mutate: refreshApp, isLoading: loadingApp } = useSWR<AppUser[]>(
    tab === 'appuser' ? API_ENDPOINTS.APP_USERS : null,
    (url) => apiGet<AppUser[]>(url)
  );

  const handleAdjust = async () => {
    if (!adjustUserId) return;
    const amount = Number(adjustAmount);
    if (!Number.isFinite(amount) || amount === 0) {
      setAdjustError('请输入非零金额（正数入账，负数扣减）');
      return;
    }
    setAdjusting(true);
    setAdjustError(null);
    try {
      await apiPost(API_ENDPOINTS.APP_USER_ADJUST_BALANCE(adjustUserId), {
        amount,
        description: adjustNote || undefined,
      });
      setAdjustUserId(null);
      setAdjustNote('');
      refreshApp();
    } catch (e) {
      setAdjustError(e instanceof Error ? e.message : '调整失败');
    } finally {
      setAdjusting(false);
    }
  };

  const refresh = () => {
    if (tab === 'admin') refreshAdmin();
    else if (tab === 'enduser') refreshEnd();
    else refreshApp();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">用户管理</h1>
          <p className="text-slate-400 mt-1">
            管理管理员、App 用户（钱包）与旧版终端用户。应用内支付关闭时，请在此为 App 用户调余额。
          </p>
        </div>
        <Button variant="outline" className="border-slate-600" onClick={refresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          刷新
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="appuser" className="data-[state=active]:bg-slate-700">
            App 用户
          </TabsTrigger>
          <TabsTrigger value="admin" className="data-[state=active]:bg-slate-700">
            管理员用户
          </TabsTrigger>
          <TabsTrigger value="enduser" className="data-[state=active]:bg-slate-700">
            终端用户（旧）
          </TabsTrigger>
        </TabsList>

        <TabsContent value="appuser">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">App 用户 ({appUsers?.length ?? 0})</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingApp ? (
                <p className="text-slate-400 text-center py-8">加载中...</p>
              ) : !appUsers?.length ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">暂无 App 用户</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-slate-300">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400">
                        <th className="text-left py-2 px-2">邮箱</th>
                        <th className="text-left py-2 px-2">姓名</th>
                        <th className="text-left py-2 px-2">余额 (COP)</th>
                        <th className="text-left py-2 px-2">状态</th>
                        <th className="text-left py-2 px-2">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {appUsers.map((u) => (
                        <tr key={u.id} className="border-b border-slate-700/50">
                          <td className="py-2 px-2">{u.email}</td>
                          <td className="py-2 px-2">{u.full_name || '—'}</td>
                          <td className="py-2 px-2 font-mono">
                            {Number(u.balance).toLocaleString('es-CO')}
                          </td>
                          <td className="py-2 px-2">
                            <Badge variant={u.status === 'active' ? 'default' : 'secondary'}>
                              {u.status}
                            </Badge>
                          </td>
                          <td className="py-2 px-2">
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-slate-600"
                              onClick={() => {
                                setAdjustUserId(u.id);
                                setAdjustAmount('10000');
                                setAdjustError(null);
                              }}
                            >
                              调余额
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {adjustUserId && (
                <div className="mt-6 p-4 rounded-lg border border-slate-600 bg-slate-900/60 space-y-3">
                  <p className="text-white text-sm font-medium">调整余额</p>
                  <p className="text-slate-400 text-xs font-mono">{adjustUserId}</p>
                  <Input
                    type="number"
                    value={adjustAmount}
                    onChange={(e) => setAdjustAmount(e.target.value)}
                    placeholder="金额（正数入账）"
                    className="bg-slate-800 border-slate-600 text-white"
                  />
                  <Input
                    value={adjustNote}
                    onChange={(e) => setAdjustNote(e.target.value)}
                    placeholder="备注（可选）"
                    className="bg-slate-800 border-slate-600 text-white"
                  />
                  {adjustError && <p className="text-red-400 text-sm">{adjustError}</p>}
                  <div className="flex gap-2">
                    <Button onClick={handleAdjust} disabled={adjusting}>
                      {adjusting ? '提交中…' : '确认'}
                    </Button>
                    <Button
                      variant="outline"
                      className="border-slate-600"
                      onClick={() => setAdjustUserId(null)}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="admin">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">管理员用户 ({adminUsers?.length ?? 0})</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingAdmin ? (
                <p className="text-slate-400 text-center py-8">加载中...</p>
              ) : !adminUsers?.length ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">暂无管理员用户</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-slate-300">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400">
                        <th className="text-left py-2 px-2">用户名</th>
                        <th className="text-left py-2 px-2">邮箱</th>
                        <th className="text-left py-2 px-2">状态</th>
                        <th className="text-left py-2 px-2">角色</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adminUsers.map((u) => (
                        <tr key={u.id} className="border-b border-slate-700/50">
                          <td className="py-2 px-2">{u.username}</td>
                          <td className="py-2 px-2">{u.email}</td>
                          <td className="py-2 px-2">
                            <Badge variant={u.is_active ? 'default' : 'destructive'}>
                              {u.is_active ? '活跃' : '禁用'}
                            </Badge>
                          </td>
                          <td className="py-2 px-2">
                            {u.is_super_admin ? '超级管理员' : '管理员'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="enduser">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">终端用户 ({endUsers?.length ?? 0})</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingEnd ? (
                <p className="text-slate-400 text-center py-8">加载中...</p>
              ) : !endUsers?.length ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">暂无终端用户</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-slate-300">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400">
                        <th className="text-left py-2 px-2">手机</th>
                        <th className="text-left py-2 px-2">ID Tag</th>
                        <th className="text-left py-2 px-2">余额</th>
                        <th className="text-left py-2 px-2">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {endUsers.map((u) => (
                        <tr key={u.id} className="border-b border-slate-700/50">
                          <td className="py-2 px-2">{u.phone}</td>
                          <td className="py-2 px-2 font-mono text-xs">{u.id_tag}</td>
                          <td className="py-2 px-2">${u.balance.toFixed(2)}</td>
                          <td className="py-2 px-2">
                            <Badge variant={u.status === 'active' ? 'default' : 'secondary'}>
                              {u.status}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
