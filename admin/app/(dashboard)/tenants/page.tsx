'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Building2, Plus } from 'lucide-react';

export default function TenantsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">租户管理</h1>
          <p className="text-slate-400 mt-1">管理系统租户（仅超级管理员）</p>
        </div>
        <Button className="bg-gradient-to-r from-purple-600 to-blue-600">
          <Plus className="h-4 w-4 mr-2" />
          添加租户
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">租户列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12">
            <Building2 className="h-12 w-12 text-slate-500 mx-auto mb-4" />
            <p className="text-slate-400">租户管理功能待实现</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}