'use client';

interface LoadingProps {
  message?: string;
}

export function Loading({ message = '加载中...' }: LoadingProps) {
  return (
    <div className="flex items-center justify-center h-full min-h-[200px]">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500 mx-auto mb-4" />
        <p className="text-slate-400">{message}</p>
      </div>
    </div>
  );
}