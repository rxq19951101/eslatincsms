'use client';

import { Component, ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';
import { useI18n } from '@/lib/i18n';

function DefaultErrorFallback({ error, reset }: { error?: Error; reset: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center min-h-[400px] p-6">
      <div className="text-center max-w-md">
        <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">{t('出现了错误')}</h2>
        <p className="text-slate-400 mb-4">{error?.message || t('发生了未知错误，请刷新页面重试')}</p>
        <Button onClick={reset} className="bg-gradient-to-r from-purple-600 to-blue-600">{t('刷新页面')}</Button>
      </div>
    </div>
  );
}

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return <DefaultErrorFallback error={this.state.error} reset={() => {
        this.setState({ hasError: false, error: undefined });
        window.location.reload();
      }} />;
    }

    return this.props.children;
  }
}
