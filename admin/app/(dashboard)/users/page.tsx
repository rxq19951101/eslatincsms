'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users, Plus } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function UsersPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">用户管理</h1>
          <p className="text-slate-400 mt-1">管理管理员用户和终端用户</p>
        </div>
        <Button className="bg-gradient-to-r from-purple-600 to-blue-600">
          <Plus className="h-4 w-4 mr-2" />
          添加用户
        </Button>
      </div>

      <Tabs defaultValue="admin" className="space-y-6">
        <TabsList className="bg-slate-800/50 border-slate-700">
          <TabsTrigger value="admin" className="data-[state=active]:bg-slate-700">
            管理员用户
          </TabsTrigger>
          <TabsTrigger value="enduser" className="data-[state=active]:bg-slate-700">
            终端用户
          </TabsTrigger>
        </TabsList>

        <TabsContent value="admin">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">管理员用户</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">管理员用户管理功能待实现</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="enduser">
          <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">终端用户</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12">
                <Users className="h-12 w-12 text-slate-500 mx-auto mb-4" />
                <p className="text-slate-400">终端用户管理功能待实现</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}