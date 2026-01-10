'use client';

import { UserMenu } from './UserMenu';
import { Bell, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export function Header() {
  return (
    <header className="h-16 bg-slate-900/80 backdrop-blur-sm border-b border-slate-800 flex items-center justify-between px-6">
      {/* Search bar */}
      <div className="hidden md:flex flex-1 max-w-md">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            type="text"
            placeholder="搜索..."
            className="pl-10 bg-slate-800/50 border-slate-700 text-slate-200 placeholder:text-slate-500 focus:border-purple-500 w-full"
          />
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <Button
          variant="ghost"
          size="icon"
          className="relative text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full" />
        </Button>

        {/* User menu */}
        <UserMenu />
      </div>
    </header>
  );
}