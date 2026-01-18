'use client';

import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Building2, ArrowRight } from 'lucide-react';

export default function ChargersPage() {
  const router = useRouter();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">充电桩管理</h1>
          <p className="text-slate-400 mt-1">该模块已迁移：请以站点为单位进行管理</p>
        </div>
        <Button onClick={() => router.push('/sites')} className="bg-gradient-to-r from-purple-600 to-blue-600">
          <Building2 className="h-4 w-4 mr-2" />
          前往站点管理
          <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
      </div>

      <Card className="bg-slate-800/80 backdrop-blur-sm border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">迁移说明</CardTitle>
        </CardHeader>
        <CardContent className="text-slate-300 space-y-2">
          <div>从现在开始，运营后台以“站点”为单位管理：</div>
          <div className="text-sm text-slate-400">
            - 在站点详情页可以查看该站点下所有充电桩，并进行“绑定/迁移充电桩到站点”等操作。
          </div>
        </CardContent>
      </Card>
    </div>
  );
}