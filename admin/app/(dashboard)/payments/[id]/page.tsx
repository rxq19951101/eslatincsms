'use client';

import { useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import useSWR from 'swr';
import { apiGet, apiPost } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, RefreshCw, CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-react';
import { useI18n } from '@/lib/i18n';

interface PaymentOrderDetail {
  id: string;
  app_user_id: string;
  user_email?: string | null;
  type: string;
  amount: number;
  currency: string;
  reference: string | null;
  external_reference?: string | null;
  status: string;
  wompi_transaction_id?: string | null;
  integrity_signature?: string | null;
  redirect_url?: string | null;
  expires_at: string;
  payment_deadline_at?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  paid_at?: string | null;
  updated_at: string;
  webhook_events: Array<{
    id: string;
    wompi_transaction_id?: string | null;
    wompi_event_id?: string | null;
    event_type?: string | null;
    processed: boolean;
    processed_at?: string | null;
    created_at: string;
  }>;
}

const fetcher = (url: string) => apiGet<PaymentOrderDetail>(url);

export default function PaymentDetailPage() {
  const { t, locale } = useI18n();
  const dateLocale = locale === 'zh-CN' ? 'zh-CN' : locale === 'es' ? 'es-CO' : 'en-US';
  const router = useRouter();
  const params = useParams();
  const orderId = params.id as string;
  const [reconciling, setReconciling] = useState(false);

  const { data: payment, error, isLoading, mutate } = useSWR<PaymentOrderDetail>(
    orderId ? API_ENDPOINTS.PAYMENT_DETAIL(orderId) : null,
    fetcher
  );

  const handleReconcile = async () => {
    if (!orderId) return;
    
    setReconciling(true);
    try {
      await apiPost(API_ENDPOINTS.PAYMENT_RECONCILE(orderId));
      await mutate();
      alert(t('对账成功'));
    } catch (error: unknown) {
      alert(`${t('对账失败')}: ${error instanceof Error ? error.message : t('请求失败')}`);
    } finally {
      setReconciling(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'approved':
        return <CheckCircle2 className="h-5 w-5 text-green-400" />;
      case 'declined':
      case 'error':
        return <XCircle className="h-5 w-5 text-red-400" />;
      case 'processing':
        return <Clock className="h-5 w-5 text-blue-400" />;
      case 'expired':
        return <AlertCircle className="h-5 w-5 text-yellow-400" />;
      default:
        return <Clock className="h-5 w-5 text-slate-400" />;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400">{t('加载中...')}</div>
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-400">{t('加载失败')}: {error?.message || 'Order not found'}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            onClick={() => router.back()}
            variant="ghost"
            size="sm"
            className="text-slate-400 hover:text-white"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            {t('返回')}
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-white">{t('支付订单详情')}</h1>
            <p className="text-slate-400 mt-1">
              {t('订单号')}: {payment.reference || payment.external_reference || t('未提供')}
            </p>
          </div>
        </div>
        <Button
          onClick={handleReconcile}
          disabled={reconciling}
          variant="outline"
          className="bg-slate-800/80 border-slate-700"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${reconciling ? 'animate-spin' : ''}`} />
          {t('对账')}
        </Button>
      </div>

      {/* 订单基本信息 */}
      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            {getStatusIcon(payment.status)}
            {t('订单信息')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('订单 ID')}</div>
              <div className="text-white font-mono">{payment.id}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('参考号')}</div>
              <div className="text-white font-mono">
                {payment.reference || payment.external_reference || t('未提供')}
              </div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('用户邮箱')}</div>
              <div className="text-white">{payment.user_email || t('未提供')}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('订单类型')}</div>
              <div className="text-white">{payment.type === 'top_up' ? t('钱包充值') : t('充电支付')}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('金额')}</div>
              <div className="text-white font-semibold">{payment.amount} {payment.currency}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('状态')}</div>
              <div className="text-white">{payment.status}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('Wompi 交易 ID')}</div>
              <div className="text-white font-mono text-sm">{payment.wompi_transaction_id || 'N/A'}</div>
            </div>
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('创建时间')}</div>
              <div className="text-white">{new Date(payment.created_at).toLocaleString(dateLocale)}</div>
            </div>
            {payment.paid_at && (
              <div>
                <div className="text-sm text-slate-400 mb-1">{t('支付时间')}</div>
                <div className="text-white">{new Date(payment.paid_at).toLocaleString(dateLocale)}</div>
              </div>
            )}
            <div>
              <div className="text-sm text-slate-400 mb-1">{t('过期时间')}</div>
              <div className="text-white">{new Date(payment.expires_at).toLocaleString(dateLocale)}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Webhook 事件记录 */}
      {payment.webhook_events && payment.webhook_events.length > 0 && (
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">{t('Webhook 事件记录')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {payment.webhook_events.map((event) => (
                <div
                  key={event.id}
                  className="p-4 bg-slate-900/50 rounded-lg border border-slate-700"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{event.event_type || 'Unknown'}</span>
                      {event.processed ? (
                        <span className="px-2 py-1 rounded text-xs bg-green-500/20 text-green-400 border border-green-500/30">
                          {t('已处理')}
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded text-xs bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                          {t('未处理')}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400">
                      {new Date(event.created_at).toLocaleString(dateLocale)}
                    </div>
                  </div>
                  <div className="text-sm text-slate-400 space-y-1">
                    <div>Transaction ID: <span className="font-mono">{event.wompi_transaction_id}</span></div>
                    <div>Event ID: <span className="font-mono">{event.wompi_event_id}</span></div>
                    {event.processed_at && (
                      <div>{t('处理时间:')} {new Date(event.processed_at).toLocaleString(dateLocale)}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 元数据 */}
      {payment.metadata && (
        <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
          <CardHeader>
            <CardTitle className="text-white">{t('元数据')}</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-slate-300 bg-slate-900/50 p-4 rounded-lg overflow-auto">
              {JSON.stringify(payment.metadata, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
