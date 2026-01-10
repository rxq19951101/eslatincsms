'use client';

import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({
  icon: Icon,
  title = '暂无数据',
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="text-center py-12">
      {Icon && <Icon className="h-12 w-12 text-slate-500 mx-auto mb-4" />}
      <h3 className="text-lg font-medium text-slate-300 mb-2">{title}</h3>
      {description && <p className="text-slate-400 mb-4">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}