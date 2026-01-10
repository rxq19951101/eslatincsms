'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings, User, Key, Building2 } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">系统设置</h1>
        <p className="text-slate-400 mt-1">管理系统配置和个人设置</p>
      </div>

      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="profile" className="data-[state=active]:bg-slate-700">
            <User className="h-4 w-4 mr-2" />
            个人信息
          </TabsTrigger>
          <TabsTrigger value="password" className="data-[state=active]:bg-slate-700">
            <Key className="h-4 w-4 mr-2" />
            修改密码
          </TabsTrigger>
          <TabsTrigger value="tenant" className="data-[state=active]:bg-slate-700">
            <Building2 className="h-4 w-4 mr-2" />
            租户设置
          </TabsTrigger>
          <TabsTrigger value="system" className="data-[state=active]:bg-slate-700">
            <Settings className="h-4 w-4 mr-2" />
            系统配置
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">个人信息</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <User className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">个人信息设置功能待实现</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="password">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">修改密码</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Key className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">修改密码功能待实现</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tenant">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">租户设置</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Building2 className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">租户设置功能待实现</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="system">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">系统配置</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Settings className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">系统配置功能待实现（仅超级管理员）</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}