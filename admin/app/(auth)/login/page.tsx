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
      try {
        const userData = await apiGet<AdminUser>(API_ENDPOINTS.AUTH_ME, {
          skipTenantId: true, // 认证接口不需要 tenant_id
        });
        setUser(userData);
      } catch (error) {
        // 如果获取用户信息失败，使用登录响应中的基本信息
        console.error('Failed to fetch user info:', error);
        setUser({
          id: response.user.id,
          username: response.user.username,
          email: response.user.email,
          full_name: response.user.full_name,
          is_super_admin: response.user.is_super_admin,
          default_tenant_id: undefined,
          tenant_list: [],
        });
      }

      // 跳转到 Dashboard
      router.push('/');
    } catch (err) {
      console.error('Login failed:', err);
      setError(err instanceof Error ? err.message : '登录失败，请检查用户名和密码');
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