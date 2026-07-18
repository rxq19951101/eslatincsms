'use client';

import { useState } from 'react';
import useSWR from 'swr';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings, User, Key, Building2 } from 'lucide-react';
import { apiGet, apiPost, apiPut } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { useI18n } from '@/lib/i18n';
import {
  configSchema,
  fieldErrors,
  passwordSchema,
  profileSchema,
  tenantSettingsSchema,
  type FieldErrors,
} from '@/lib/validation';

interface ConfigRecord {
  tenant_id?: string | null;
  config_key: string;
  config_value: unknown;
}

interface TenantSettings {
  name: string;
  domain?: string | null;
}

export default function SettingsPage() {
  const user = useAuthStore((state) => state.user);
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const { t } = useI18n();
  const { data: configs, mutate: refreshConfigs } = useSWR<ConfigRecord[]>(
    API_ENDPOINTS.CONFIGS,
    (url: string) => apiGet<ConfigRecord[]>(url)
  );
  const [configKey, setConfigKey] = useState('');
  const [configValue, setConfigValue] = useState('');
  const [tenantName, setTenantName] = useState(currentTenant?.name || '');
  const [tenantDomain, setTenantDomain] = useState('');
  const [tenantMessage, setTenantMessage] = useState<string | null>(null);
  const [tenantErrors, setTenantErrors] = useState<FieldErrors>({});
  useSWR<TenantSettings>(
    currentTenant ? API_ENDPOINTS.TENANT_CURRENT : null,
    (url: string) => apiGet<TenantSettings>(url),
    {
      onSuccess: (settings) => {
        setTenantName(settings.name || '');
        setTenantDomain(settings.domain || '');
      },
    }
  );
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileErrors, setProfileErrors] = useState<FieldErrors>({});
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordErrors, setPasswordErrors] = useState<FieldErrors>({});
  const [configErrors, setConfigErrors] = useState<FieldErrors>({});

  const handleChangePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPasswordMessage(null);
    setPasswordError(null);
    const result = passwordSchema.safeParse({ old_password: oldPassword, new_password: newPassword, confirm_password: confirmPassword });
    if (!result.success) {
      setPasswordErrors(fieldErrors(result.error));
      return;
    }
    setPasswordErrors({});
    try {
      await apiPut(API_ENDPOINTS.AUTH_CHANGE_PASSWORD, { old_password: result.data.old_password, new_password: result.data.new_password });
      setOldPassword(''); setNewPassword(''); setConfirmPassword('');
      setPasswordMessage(t('密码修改成功'));
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : t('密码修改失败'));
    }
  };
  const handleSaveConfig = async (event: React.FormEvent) => {
    event.preventDefault();
    const registeredKeys = new Set((configs || []).map((config) => config.config_key));
    const result = configSchema.safeParse({ config_key: configKey, config_value: configValue });
    if (!result.success || !registeredKeys.has(configKey)) {
      setConfigErrors(result.success ? { config_key: 'validation.configKey' } : fieldErrors(result.error));
      return;
    }
    setConfigErrors({});
    await apiPost(API_ENDPOINTS.CONFIGS, { ...result.data, value_type: 'string' });
    setConfigValue(''); await refreshConfigs();
  };
  const handleSaveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = profileSchema.safeParse({ full_name: fullName, email });
    if (!result.success) {
      setProfileErrors(fieldErrors(result.error));
      return;
    }
    setProfileErrors({});
    const updated = await apiPut<{ full_name?: string; email: string }>(API_ENDPOINTS.AUTH_UPDATE_PROFILE, result.data);
    useAuthStore.getState().setUser({ ...useAuthStore.getState().user!, full_name: updated.full_name, email: updated.email });
    setProfileMessage(t('个人资料已更新'));
  };
  const handleSaveTenant = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentTenant) return;
    const result = tenantSettingsSchema.safeParse({ name: tenantName, domain: tenantDomain });
    if (!result.success) {
      setTenantErrors(fieldErrors(result.error));
      return;
    }
    setTenantErrors({});
    await apiPut(API_ENDPOINTS.TENANT_CURRENT, { name: result.data.name, domain: result.data.domain || null });
    setTenantMessage(t('租户资料已更新'));
  };
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">{t('系统设置')}</h1>
        <p className="text-slate-400 mt-1">{t('管理系统配置和个人设置')}</p>
      </div>

      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="profile" className="data-[state=active]:bg-slate-700">
            <User className="h-4 w-4 mr-2" />
            {t('个人信息')}
          </TabsTrigger>
          <TabsTrigger value="password" className="data-[state=active]:bg-slate-700">
            <Key className="h-4 w-4 mr-2" />
            {t('修改密码')}
          </TabsTrigger>
          <TabsTrigger value="tenant" className="data-[state=active]:bg-slate-700">
            <Building2 className="h-4 w-4 mr-2" />
            {t('租户设置')}
          </TabsTrigger>
          <TabsTrigger value="system" className="data-[state=active]:bg-slate-700">
            <Settings className="h-4 w-4 mr-2" />
            {t('系统配置')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('个人信息')}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveProfile} className="max-w-md space-y-4">
                <p className="text-sm text-slate-400">{t('用户名：')}{user?.username}</p>
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" placeholder={t('姓名')} value={fullName} onChange={(e) => setFullName(e.target.value)} aria-invalid={!!profileErrors.full_name} />
                {profileErrors.full_name && <p className="text-sm text-red-400">{t(profileErrors.full_name)}</p>}
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" type="email" placeholder={t('邮箱')} value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!profileErrors.email} />
                {profileErrors.email && <p className="text-sm text-red-400">{t(profileErrors.email)}</p>}
                {profileMessage && <p className="text-sm text-emerald-400">{profileMessage}</p>}
                <button type="submit" className="rounded bg-purple-600 px-4 py-2 text-white">{t('保存资料')}</button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="password">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('修改密码')}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleChangePassword} className="max-w-md space-y-4">
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" type="password" placeholder={t('当前密码')} value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} aria-invalid={!!passwordErrors.old_password} />
                {passwordErrors.old_password && <p className="text-sm text-red-400">{t(passwordErrors.old_password)}</p>}
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" type="password" placeholder={t('新密码（至少 8 位）')} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} aria-invalid={!!passwordErrors.new_password} />
                {passwordErrors.new_password && <p className="text-sm text-red-400">{t(passwordErrors.new_password)}</p>}
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" type="password" placeholder={t('确认新密码')} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} aria-invalid={!!passwordErrors.confirm_password} />
                {passwordErrors.confirm_password && <p className="text-sm text-red-400">{t(passwordErrors.confirm_password)}</p>}
                {passwordError && <p className="text-sm text-red-400">{passwordError}</p>}
                {passwordMessage && <p className="text-sm text-emerald-400">{passwordMessage}</p>}
                <button type="submit" className="rounded bg-purple-600 px-4 py-2 text-white">{t('保存密码')}</button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tenant">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('租户设置')}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveTenant} className="max-w-md space-y-4">
                <Building2 className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-sm text-slate-400">{t('当前租户：')}{currentTenant?.name || t('未选择')}</p>
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" placeholder={t('租户名称')} value={tenantName} onChange={(e) => setTenantName(e.target.value)} disabled={!currentTenant} aria-invalid={!!tenantErrors.name} />
                {tenantErrors.name && <p className="text-sm text-red-400">{t(tenantErrors.name)}</p>}
                <input className="w-full rounded border border-slate-600 bg-slate-700 p-2 text-white" placeholder={t('域名（可选）')} value={tenantDomain} onChange={(e) => setTenantDomain(e.target.value)} disabled={!currentTenant} aria-invalid={!!tenantErrors.domain} />
                {tenantErrors.domain && <p className="text-sm text-red-400">{t(tenantErrors.domain)}</p>}
                {tenantMessage && <p className="text-sm text-emerald-400">{tenantMessage}</p>}
                <button type="submit" className="rounded bg-purple-600 px-4 py-2 text-white" disabled={!currentTenant}>{t('保存租户资料')}</button>
              </form>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="system">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">{t('系统配置')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Settings className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <div className="space-y-3">
                  {(configs || []).map((config) => (
                    <div key={`${config.tenant_id || 'global'}:${config.config_key}`} className="flex justify-between rounded bg-slate-700/60 p-3 text-sm">
                      <span className="text-slate-300">{config.config_key}</span>
                      <span className="text-slate-400">{String(config.config_value)}</span>
                    </div>
                  ))}
                  <form onSubmit={handleSaveConfig} className="flex gap-2 pt-3">
                    <select className="flex-1 rounded border border-slate-600 bg-slate-700 p-2 text-white" value={configKey} onChange={(e) => setConfigKey(e.target.value)} aria-label={t('配置键')}>
                      <option value="">{t('选择已注册配置键')}</option>
                      {(configs || []).map((config) => <option key={config.config_key} value={config.config_key}>{config.config_key}</option>)}
                    </select>
                    <input className="flex-1 rounded border border-slate-600 bg-slate-700 p-2 text-white" placeholder={t('配置值')} value={configValue} onChange={(e) => setConfigValue(e.target.value)} />
                    <button type="submit" className="rounded bg-purple-600 px-3 text-white">{t('保存')}</button>
                  </form>
                  {configErrors.config_key && <p className="text-sm text-red-400">{t(configErrors.config_key)}</p>}
                  {configErrors.config_value && <p className="text-sm text-red-400">{t(configErrors.config_value)}</p>}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
