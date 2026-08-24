'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, RefreshCw, Eye } from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { matchesSearchQuery } from '@/lib/search';
import { useAuthStore } from '@/store/authStore';

interface PaymentOrder {
  id: string;
  app_user_id: string;
  user_email?: string | null;
  type: string;
  amount: number;
  currency: string;
  reference: string | null;
  external_reference?: string | null;
  status: string;
  wompi_transaction_id?: string;
  created_at: string;
  paid_at?: string;
}

const fetcher = (url: string) => apiGet<PaymentOrder[]>(url);

export default function PaymentsPage() {
  const router = useRouter();
  const { t, locale } = useI18n();
  const user = useAuthStore((state) => state.user);
  const canManagePlatformPayments = !!user?.is_super_admin;
  const dateLocale = locale === 'zh-CN' ? 'zh-CN' : locale === 'es' ? 'es-CO' : 'en-US';
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const { data: payments, error, isLoading, mutate } = useSWR<PaymentOrder[]>(
    canManagePlatformPayments ? `${API_ENDPOINTS.PAYMENTS}?limit=100&offset=0` : null,
    fetcher,
    {
      refreshInterval: 30000,
    }
  );

  const filteredPayments = payments?.filter((payment) => {
    const matchesSearch = matchesSearchQuery(searchQuery, [
      payment.reference,
      payment.external_reference,
      payment.user_email,
      payment.id,
    ]);
    const matchesStatus = statusFilter === 'all' || payment.status === statusFilter;
    const matchesType = typeFilter === 'all' || payment.type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'approved':
        return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'declined':
      case 'error':
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 'processing':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'expired':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  if (!canManagePlatformPayments) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">{t('仅超级管理员可以管理平台支付')}</div>
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
        <div className="text-red-400">{t('加载失败')}: {error.message}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">{t('支付管理')}</h1>
          <p className="text-slate-400 mt-1">{t('查看和管理所有支付订单（Wompi）')}</p>
        </div>
        <Button onClick={() => mutate()} variant="outline" className="bg-slate-800/80 border-slate-700">
          <RefreshCw className="h-4 w-4 mr-2" />
          {t('刷新')}
        </Button>
      </div>

      {/* 筛选器 */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder={t('搜索订单号、用户邮箱...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-slate-900/50 border-slate-700 text-white"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="bg-slate-900/50 border-slate-700 text-white">
                <SelectValue placeholder={t('订单状态')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('全部状态')}</SelectItem>
                <SelectItem value="created">{t('已创建')}</SelectItem>
                <SelectItem value="processing">{t('处理中')}</SelectItem>
                <SelectItem value="approved">{t('已批准')}</SelectItem>
                <SelectItem value="declined">{t('已拒绝')}</SelectItem>
                <SelectItem value="error">{t('错误')}</SelectItem>
                <SelectItem value="expired">{t('已过期')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="bg-slate-900/50 border-slate-700 text-white">
                <SelectValue placeholder={t('订单类型')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('全部类型')}</SelectItem>
                <SelectItem value="top_up">{t('钱包充值')}</SelectItem>
                <SelectItem value="charging">{t('充电支付')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* 支付订单列表 */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('支付订单列表')}</CardTitle>
        </CardHeader>
        <CardContent>
          {filteredPayments && filteredPayments.length > 0 ? (
            <div className="space-y-4">
              {filteredPayments.map((payment) => (
                <div
                  key={payment.id}
                  className="flex items-center justify-between p-4 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-slate-600 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="font-semibold text-white">
                        {payment.reference || payment.external_reference || t('未提供')}
                      </span>
                      <span className={`px-2 py-1 rounded text-xs font-medium border ${getStatusBadgeColor(payment.status)}`}>
                        {payment.status}
                      </span>
                    </div>
                    <div className="text-sm text-slate-400 space-y-1">
                      <div>{t('用户:')} {payment.user_email || t('未提供')}</div>
                      <div>{t('类型:')} {payment.type === 'top_up' ? t('钱包充值') : t('充电支付')}</div>
                      <div>{t('金额:')} {payment.amount} {payment.currency}</div>
                      <div>{t('创建时间:')} {new Date(payment.created_at).toLocaleString(dateLocale)}</div>
                      {payment.paid_at && (
                        <div>{t('支付时间:')} {new Date(payment.paid_at).toLocaleString(dateLocale)}</div>
                      )}
                    </div>
                  </div>
                  <Button
                    onClick={() => router.push(`/payments/${payment.id}`)}
                    variant="outline"
                    size="sm"
                    className="bg-slate-800/80 border-slate-700"
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    {t('查看详情')}
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              {t('暂无支付订单')}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
