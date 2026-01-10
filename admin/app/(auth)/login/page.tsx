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
import { LoginRequest, LoginResponse, AdminUser } from '@/types';
import { Zap } from 'lucide-react';

const loginSchema = z.object({
  username: z.string().min(1, '用户名不能为空'),
  password: z.string().min(1, '密码不能为空'),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuthStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      // 存储 token
      setTokens(response.access_token, response.refresh_token);

      // 获取完整的用户信息（包含租户列表）
      // #region agent log
      try {
        fetch('http://127.0.0.1:7242/ingest/ef49133c-edf7-44f0-b6da-8a7d43918316', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            location: 'login/page.tsx:after_login',
            message: 'Login successful, attempting to fetch /me',
            data: {
              login_response_user: response.user,
              has_default_tenant_id: !!response.user.default_tenant_id,
              default_tenant_id: response.user.default_tenant_id
            },
            timestamp: Date.now(),
            sessionId: 'debug-session',
            runId: 'run1',
            hypothesisId: 'A'
          })
        }).catch(() => {});
      } catch {}
      // #endregion
      
      try {
        const userData = await apiGet<AdminUser>(API_ENDPOINTS.AUTH_ME, {
          skipTenantId: true, // /me 接口应该能够自动处理（已跳过 tenant_middleware 检查）
        });
        
        // #region agent log
        try {
          fetch('http://127.0.0.1:7242/ingest/ef49133c-edf7-44f0-b6da-8a7d43918316', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              location: 'login/page.tsx:/me_success',
              message: '/me endpoint returned user data',
              data: {
                has_default_tenant_id: !!userData.default_tenant_id,
                default_tenant_id: userData.default_tenant_id,
                tenant_list_size: userData.tenant_list?.length || 0
              },
              timestamp: Date.now(),
              sessionId: 'debug-session',
              runId: 'run1',
              hypothesisId: 'A'
            })
          }).catch(() => {});
        } catch {}
        // #endregion
        
        setUser(userData);
      } catch (error) {
        // #region agent log
        try {
          fetch('http://127.0.0.1:7242/ingest/ef49133c-edf7-44f0-b6da-8a7d43918316', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              location: 'login/page.tsx:/me_failed',
              message: '/me endpoint failed, using fallback',
              data: {
                error: error instanceof Error ? error.message : String(error),
                login_response_has_tenant_id: !!response.user.default_tenant_id
              },
              timestamp: Date.now(),
              sessionId: 'debug-session',
              runId: 'run1',
              hypothesisId: 'A'
            })
          }).catch(() => {});
        } catch {}
        // #endregion
        
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
      }

      // 跳转到 Dashboard
      router.push('/');
    } catch (err) {
      console.error('Login failed:', err);
      
      // 处理不同类型的错误
      let errorMessage = '登录失败，请稍后重试';
      
      if (err instanceof Error) {
        const message = err.message.toLowerCase();
        
        // 网络错误
        if (message.includes('failed to fetch') || message.includes('network')) {
          errorMessage = '网络连接失败，请检查网络或后端服务是否正常运行';
        }
        // 401 认证错误（用户名或密码错误）
        else if (message.includes('401') || message.includes('unauthorized') || 
                 message.includes('invalid username or password') ||
                 message.includes('用户名或密码错误')) {
          errorMessage = '用户名或密码错误，请重新输入';
        }
        // 403 账户被禁用
        else if (message.includes('403') || message.includes('forbidden') || 
                 message.includes('inactive')) {
          errorMessage = '账户已被禁用，请联系管理员';
        }
        // 500 服务器错误
        else if (message.includes('500') || message.includes('internal server error')) {
          errorMessage = '服务器内部错误，请联系技术支持';
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
            <div className="p-3 bg-purple-600/20 rounded-full">
              <Zap className="h-8 w-8 text-purple-400" />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold text-white">充电桩运营平台</CardTitle>
          <CardDescription className="text-slate-400">
            请输入您的账号和密码登录
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {error && (
              <div className="p-3 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-md">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="username" className="text-slate-300">
                用户名
              </Label>
              <Input
                id="username"
                type="text"
                placeholder="请输入用户名"
                className="bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-purple-500"
                {...register('username')}
                disabled={isLoading}
              />
              {errors.username && (
                <p className="text-sm text-red-400">{errors.username.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-300">
                密码
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="请输入密码"
                className="bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-purple-500"
                {...register('password')}
                disabled={isLoading}
              />
              {errors.password && (
                <p className="text-sm text-red-400">{errors.password.message}</p>
              )}
            </div>

            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white"
              disabled={isLoading}
            >
              {isLoading ? '登录中...' : '登录'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}