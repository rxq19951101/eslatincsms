'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Transaction } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, Download, FileText } from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { matchesSearchQuery } from '@/lib/search';
import {
  formatDateTime,
  formatMeasurement,
  getStatusBadgeClass,
  getStatusMessageKey,
  isOngoingStatus,
} from '@/lib/localization';

const fetcher = (url: string) => apiGet<Transaction[]>(url);

export default function TransactionsPage() {
  const { t, locale } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data: transactions, error, isLoading } = useSWR<Transaction[]>(
    API_ENDPOINTS.TRANSACTIONS + `?limit=100&offset=0`,
    fetcher,
    {
      refreshInterval: 30000,
    }
  );

  const filteredTransactions = transactions?.filter((tx) => {
    const matchesSearch = matchesSearchQuery(searchQuery, [tx.transaction_id, tx.ocpp_identity]);
    const matchesStatus = statusFilter === 'all' || tx.status?.toLowerCase() === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const handleExport = () => {
    // TODO: 实现导出功能
    alert(t('导出功能待实现'));
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
          <h1 className="text-3xl font-bold text-white">{t('交易管理')}</h1>
          <p className="text-slate-400 mt-1">{t('查看和管理所有充电交易记录')}</p>
        </div>
        <Button onClick={handleExport} className="bg-gradient-to-r from-purple-600 to-blue-600">
          <Download className="h-4 w-4 mr-2" />
          {t('导出数据')}
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                type="text"
                placeholder={t('搜索 OCPP 交易号、OCPP 身份...')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-slate-700/50 border-slate-600"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full md:w-[180px] bg-slate-700/50 border-slate-600">
                <SelectValue placeholder={t('筛选状态')} />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="all">{t('全部状态')}</SelectItem>
                <SelectItem value="ongoing">{t('status.ongoing')}</SelectItem>
                <SelectItem value="completed">{t('status.completed')}</SelectItem>
                <SelectItem value="cancelled">{t('status.cancelled')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{t('交易列表')}</CardTitle>
        </CardHeader>
        <CardContent>
          {filteredTransactions && filteredTransactions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('OCPP 交易号')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('OCPP 身份')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('开始时间')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('结束时间')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('充电量 (kWh)')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('时长 (分钟)')}</th>
                    <th className="text-left py-3 px-4 text-slate-400 font-medium">{t('状态')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((tx) => {
                    const fallback = t('common.notAvailable');
                    return (
                      <tr key={tx.id} data-testid="admin-transaction-row" className="border-b border-slate-700/50 hover:bg-slate-700/30">
                        <td className="py-3 px-4 text-white">{tx.transaction_id ?? fallback}</td>
                        <td className="py-3 px-4 text-slate-300" data-testid="transaction-ocpp-identity">
                          {tx.ocpp_identity?.trim() || fallback}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {formatDateTime(tx.start_time, locale, fallback)}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {tx.end_time
                            ? formatDateTime(tx.end_time, locale, fallback)
                            : isOngoingStatus(tx.status) ? t('status.ongoing') : fallback}
                        </td>
                        <td className="py-3 px-4 text-slate-300">{formatMeasurement(tx.energy_kwh, 2, '', fallback)}</td>
                        <td className="py-3 px-4 text-slate-300">{formatMeasurement(tx.duration_minutes, 1, '', fallback)}</td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-2 py-1 rounded-md text-xs ${getStatusBadgeClass(tx.status)}`}
                          >
                            {t(getStatusMessageKey(tx.status))}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-slate-500 mx-auto mb-4" />
              <p className="text-slate-400">{t('没有找到交易记录')}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
