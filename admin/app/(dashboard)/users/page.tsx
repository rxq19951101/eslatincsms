'use client';

import { useRef, useState } from 'react';
import useSWR from 'swr';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Users, RefreshCw } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useI18n } from '@/lib/i18n';
import {
  apiErrorMessageKey,
  apiFieldErrors,
  fieldErrors,
  walletAdjustmentSchema,
  WALLET_API_FIELD_MAPPING,
  type FieldErrors,
} from '@/lib/validation';
import { IdempotencyIntentStore, requestIntent } from '@/lib/idempotency';

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
  const [adjustErrors, setAdjustErrors] = useState<FieldErrors>({});
  const adjustmentIntents = useRef(new IdempotencyIntentStore()).current;
  const { t } = useI18n();

  const { data: adminUsers, mutate: refreshAdmin, isLoading: loadingAdmin } = useSWR<AdminUser[]>(
    tab === 'admin' ? API_ENDPOINTS.ADMIN_USERS : null,
    (url: string) => apiGet<AdminUser[]>(url)
  );

  const { data: appUsers, mutate: refreshApp, isLoading: loadingApp } = useSWR<AppUser[]>(
    tab === 'appuser' ? API_ENDPOINTS.APP_USERS : null,
    (url: string) => apiGet<AppUser[]>(url)
  );

  const handleAdjust = async () => {
    if (!adjustUserId) return;
    const result = walletAdjustmentSchema.safeParse({ amount: adjustAmount, description: adjustNote });
    if (!result.success) {
      setAdjustErrors(fieldErrors(result.error));
      setAdjustError(null);
      return;
    }
    setAdjusting(true);
    setAdjustError(null);
    setAdjustErrors({});
    const payload = {
      amount: result.data.amount,
      description: result.data.description,
    };
    const intent = requestIntent(`wallet-adjust:${adjustUserId}`, payload);
    const idempotencyKey = adjustmentIntents.keyFor(intent);
    try {
      await apiPost(API_ENDPOINTS.APP_USER_ADJUST_BALANCE(adjustUserId), {
        ...payload,
        idempotency_key: idempotencyKey,
      });
      adjustmentIntents.markSucceeded(intent);
      setAdjustUserId(null);
      setAdjustNote('');
      refreshApp();
    } catch (e) {
      setAdjustErrors(apiFieldErrors(e, WALLET_API_FIELD_MAPPING));
      setAdjustError(t(apiErrorMessageKey(e, '调整失败')));
    } finally {
      setAdjusting(false);
    }
  };

  const refresh = () => {
    if (tab === 'admin') refreshAdmin();
    else refreshApp();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('users')}</h1>
          <p className="text-slate-400 mt-1">
            {t('adminUsersAndAppUsers')}
          </p>
        </div>
        <Button variant="outline" className="border-slate-600" onClick={refresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          {t('refresh')}
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="appuser" className="data-[state=active]:bg-slate-700">
            {t('appUsers')}
          </TabsTrigger>
          <TabsTrigger value="admin" className="data-[state=active]:bg-slate-700">
            {t('adminUsers')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="appuser">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t(`App 用户 (${appUsers?.length ?? 0})`)}</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingApp ? (
                <p className="text-slate-400 text-center py-8">{t('加载中...')}</p>
              ) : !appUsers?.length ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">{t('暂无 App 用户')}</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-slate-300">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400">
                        <th className="text-left py-2 px-2">{t('邮箱')}</th>
                        <th className="text-left py-2 px-2">{t('姓名')}</th>
                        <th className="text-left py-2 px-2">{t('余额 (COP)')}</th>
                        <th className="text-left py-2 px-2">{t('状态')}</th>
                        <th className="text-left py-2 px-2">{t('操作')}</th>
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
                                adjustmentIntents.clear();
                                setAdjustUserId(u.id);
                                setAdjustAmount('10000');
                                setAdjustNote('');
                                setAdjustError(null);
                                setAdjustErrors({});
                              }}
                            >
                              {t('调余额')}
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
                  <p className="text-white text-sm font-medium">{t('调整余额')}</p>
                  <p className="text-slate-400 text-sm">{appUsers?.find((user) => user.id === adjustUserId)?.email}</p>
                  <Input
                    type="number"
                    step="0.01"
                    value={adjustAmount}
                    onChange={(e) => setAdjustAmount(e.target.value)}
                    placeholder={t('金额（正数入账）')}
                    aria-invalid={!!adjustErrors.amount}
                    className="bg-slate-800 border-slate-600 text-white"
                  />
                  {adjustErrors.amount && <p className="text-red-400 text-sm">{t(adjustErrors.amount)}</p>}
                  <Input
                    value={adjustNote}
                    onChange={(e) => setAdjustNote(e.target.value)}
                    placeholder={t('调整原因（必填）')}
                    aria-invalid={!!adjustErrors.description}
                    className="bg-slate-800 border-slate-600 text-white"
                  />
                  {adjustErrors.description && <p className="text-red-400 text-sm">{t(adjustErrors.description)}</p>}
                  {adjustError && <p className="text-red-400 text-sm">{adjustError}</p>}
                  <div className="flex gap-2">
                    <Button onClick={handleAdjust} disabled={adjusting}>
                      {adjusting ? t('提交中…') : t('确认')}
                    </Button>
                    <Button
                      variant="outline"
                      className="border-slate-600"
                      onClick={() => {
                        adjustmentIntents.clear();
                        setAdjustUserId(null);
                      }}
                    >
                      {t('取消')}
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
              <CardTitle className="text-white">{t(`管理员用户 (${adminUsers?.length ?? 0})`)}</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingAdmin ? (
                <p className="text-slate-400 text-center py-8">{t('加载中...')}</p>
              ) : !adminUsers?.length ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                  <p className="text-slate-400">{t('暂无管理员用户')}</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-slate-300">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400">
                        <th className="text-left py-2 px-2">{t('用户名')}</th>
                        <th className="text-left py-2 px-2">{t('邮箱')}</th>
                        <th className="text-left py-2 px-2">{t('状态')}</th>
                        <th className="text-left py-2 px-2">{t('角色')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adminUsers.map((u) => (
                        <tr key={u.id} className="border-b border-slate-700/50">
                          <td className="py-2 px-2">{u.username}</td>
                          <td className="py-2 px-2">{u.email}</td>
                          <td className="py-2 px-2">
                            <Badge variant={u.is_active ? 'default' : 'destructive'}>
                              {u.is_active ? t('活跃') : t('禁用')}
                            </Badge>
                          </td>
                          <td className="py-2 px-2">
                            {u.is_super_admin ? t('超级管理员') : t('管理员')}
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
