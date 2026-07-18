'use client';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { CreditCard, CheckCircle2, XCircle, Eye, EyeOff } from 'lucide-react';
import { useI18n } from '@/lib/i18n';

export default function PaymentsSettingsPage() {
  const { t } = useI18n();
  // 这些值应该从环境变量或配置中获取（只读显示）
  const wompiConfig = {
    environment: process.env.NEXT_PUBLIC_WOMPI_ENVIRONMENT || 'sandbox',
    publicKeySandbox: process.env.NEXT_PUBLIC_WOMPI_PUBLIC_KEY_SANDBOX || '',
    publicKeyProd: process.env.NEXT_PUBLIC_WOMPI_PUBLIC_KEY_PROD || '',
    hasPrivateKey: !!process.env.WOMPI_PRIVATE_KEY_SANDBOX || !!process.env.WOMPI_PRIVATE_KEY_PROD,
  };

  const maskKey = (key: string) => {
    if (!key || key.length < 8) return '****';
    return `${key.substring(0, 4)}****${key.substring(key.length - 4)}`;
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">{t('支付配置')}</h1>
        <p className="text-slate-400 mt-1">{t('查看支付配置状态（当前版本默认关闭应用内支付）')}</p>
      </div>

      <Card className="bg-amber-950/40 border-amber-700/50">
        <CardHeader>
          <CardTitle className="text-amber-200 text-base">{t('应用内支付轨已关闭')}</CardTitle>
          <CardDescription className="text-amber-200/80">
            {t('当前应用内支付功能默认关闭。用户余额可在用户管理中调整；接入第三方支付后再启用服务端支付配置。')}
          </CardDescription>
        </CardHeader>
      </Card>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            {t('Wompi 配置信息')}
          </CardTitle>
          <CardDescription className="text-slate-400">
            {t('Private Key 和 Integrity Secret 通过环境变量配置，不在界面中显示')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-slate-400 mb-2">{t('环境')}</div>
              <div className="flex items-center gap-2">
                <span className="text-white font-semibold">
                  {wompiConfig.environment === 'sandbox' ? t('沙盒环境') : t('生产环境')}
                </span>
                {wompiConfig.environment === 'sandbox' ? (
                  <span className="px-2 py-1 rounded text-xs bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                    {t('测试')}
                  </span>
                ) : (
                  <span className="px-2 py-1 rounded text-xs bg-green-500/20 text-green-400 border border-green-500/30">
                    {t('生产')}
                  </span>
                )}
              </div>
            </div>

            <div>
              <div className="text-sm text-slate-400 mb-2">{t('Private Key 状态')}</div>
              <div className="flex items-center gap-2">
                {wompiConfig.hasPrivateKey ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-green-400" />
                    <span className="text-white">{t('已配置')}</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-red-400" />
                    <span className="text-red-400">{t('未配置')}</span>
                  </>
                )}
              </div>
            </div>

            <div>
              <div className="text-sm text-slate-400 mb-2">Public Key (Sandbox)</div>
              <div className="text-white font-mono text-sm">
                {wompiConfig.publicKeySandbox ? maskKey(wompiConfig.publicKeySandbox) : t('未配置')}
              </div>
            </div>

            <div>
              <div className="text-sm text-slate-400 mb-2">Public Key (Production)</div>
              <div className="text-white font-mono text-sm">
                {wompiConfig.publicKeyProd ? maskKey(wompiConfig.publicKeyProd) : t('未配置')}
              </div>
            </div>
          </div>

          <div className="mt-6 p-4 bg-slate-900/50 rounded-lg border border-slate-700">
            <div className="text-sm text-slate-400 space-y-1">
              <div className="font-semibold text-slate-300 mb-2">{t('配置说明：')}</div>
              <div>• {t('Private Key 和 Integrity Secret 存储在服务端环境变量中')}</div>
              <div>• {t('这些敏感信息不会在界面中显示')}</div>
              <div>• {t('如需修改配置，请更新服务端环境变量并重启服务')}</div>
              <div>• {t('Webhook URL 在 Wompi 后台配置')}</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
