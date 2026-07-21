'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiPost, apiGet } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { setTokens } from '@/lib/auth';
import { useAuthStore } from '@/store/authStore';
import { useTenantStore } from '@/store/tenantStore';
import { getDefaultTenant } from '@/lib/tenant';
import { LoginRequest, LoginResponse, AdminUser } from '@/types';
import { useI18n } from '@/lib/i18n';
import Image from 'next/image';

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuthStore();
  const { setCurrentTenant, clearTenant } = useTenantStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await apiPost<LoginResponse>(
        API_ENDPOINTS.AUTH_LOGIN,
        data as LoginRequest,
        {
          skipAuth: true,
          skipTenantId: true,
        }
      );

      // 登录成功即开始一个干净的账号会话，绝不继承前一管理员的租户上下文。
      clearTenant();
      setUser(null);
      setTokens(response.access_token, response.refresh_token);

      // 获取完整的用户信息（包含租户列表）
      try {
        const userData = await apiGet<AdminUser>(API_ENDPOINTS.AUTH_ME, {
          skipTenantId: true, // /me 接口应该能够自动处理（已跳过 tenant_middleware 检查）
        });
        setUser(userData);
        // super_admin 默认保持全平台；普通管理员自动进入当前账号的有效默认租户。
        const selected = getDefaultTenant(userData);
        setCurrentTenant(selected, userData.id);
      } catch (error) {
        // 如果获取用户信息失败，使用登录响应中的基本信息（如果包含 default_tenant_id）
        console.error('Failed to fetch user info:', error);
        setUser({
          id: response.user.id,
          username: response.user.username,
          email: response.user.email,
          full_name: response.user.full_name,
          is_super_admin: response.user.is_super_admin,
          default_tenant_id: response.user.default_tenant_id, // 使用登录响应中的 default_tenant_id
          tenant_list: [],
        });
        // fallback 没有可验证成员关系，因此保持无租户上下文，避免使用不可信默认值。
      }

      // 跳转到 Dashboard
      router.push('/');
    } catch (err) {
      console.error('Login failed:', err);
      
      // 处理不同类型的错误
      let errorMessage = t('loginFailed');
      
      if (err instanceof Error) {
        const message = err.message.toLowerCase();
        
        // 网络错误
        if (message.includes('failed to fetch') || message.includes('network')) {
          errorMessage = t('networkError');
        }
        // 401 认证错误（用户名或密码错误）
        else if (message.includes('401') || message.includes('unauthorized') || 
                 message.includes('invalid username or password') ||
                 message.includes('用户名或密码错误')) {
          errorMessage = t('invalidCredentials');
        }
        // 403 账户被禁用
        else if (message.includes('403') || message.includes('forbidden') || 
                 message.includes('inactive')) {
          errorMessage = t('账户已被禁用，请联系管理员');
        }
        // 500 服务器错误
        else if (message.includes('500') || message.includes('internal server error')) {
          errorMessage = t('服务器内部错误，请联系技术支持');
        }
        // 其他错误，显示原始消息
        else if (err.message) {
          errorMessage = err.message;
        }
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-4">
      <Card className="w-full max-w-md bg-slate-800/80 backdrop-blur-lg border-slate-700 shadow-xl">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <Image src="/brand/eslatin-full-dark.svg" alt="EsLatin" width={360} height={296} loading="eager" className="h-32 w-auto object-contain" />
          </div>
          <CardTitle className="text-2xl font-bold text-white">{t('loginTitle')}</CardTitle>
          <CardDescription className="text-slate-400">
            {t('loginSubtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {error && (
              <div data-testid="admin-login-error" role="alert" className="p-3 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-md">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="username" className="text-slate-300">
                {t('username')}
              </Label>
              <Input
                data-testid="admin-login-username"
                id="username"
                type="text"
                placeholder={t('usernamePlaceholder')}
                className="bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-purple-500"
                {...register('username')}
                disabled={isLoading}
              />
              {errors.username && (
                <p className="text-sm text-red-400">{t('usernameRequired')}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-300">
                {t('password')}
              </Label>
              <Input
                data-testid="admin-login-password"
                id="password"
                type="password"
                placeholder={t('passwordPlaceholder')}
                className="bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-purple-500"
                {...register('password')}
                disabled={isLoading}
              />
              {errors.password && (
                <p className="text-sm text-red-400">{t('passwordRequired')}</p>
              )}
            </div>

            <Button
              data-testid="admin-login-submit"
              type="submit"
              className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white"
              disabled={isLoading}
            >
              {isLoading ? t('loggingIn') : t('login')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
