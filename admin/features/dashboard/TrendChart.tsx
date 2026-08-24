'use client';

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { TrendDataPoint } from '@/types';
import { useI18n } from '@/lib/i18n';
import { formatDate } from '@/lib/localization';

interface TrendChartProps {
  data: TrendDataPoint[];
  title: string;
  color: string;
  unit?: string;
  valueFormatter?: (value: number) => string;
  /** 图表像素高度，需与外层容器一致，避免 ResponsiveContainer 读到 width/height=-1 */
  chartHeight?: number;
}

export function TrendChart({ data, title, color, unit = '', valueFormatter, chartHeight = 256 }: TrendChartProps) {
  const { locale, t } = useI18n();
  const fallback = t('common.notAvailable');
  const formatChartDate = (dateStr: string | number) => formatDate(dateStr, locale, fallback);

  // 格式化数值显示
  const formatValue = (value: unknown) => {
    const numericValue = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(numericValue)) return fallback;
    if (valueFormatter) return valueFormatter(numericValue);
    if (unit === 'kWh') {
      return `${numericValue.toFixed(2)} kWh`;
    }
    return numericValue.toFixed(0);
  };

  // 从 CSS variable 获取颜色
  const primaryColor = color || 'hsl(var(--chart-primary))';

  return (
    <div
      className="w-full min-w-0"
      style={{ height: chartHeight }}
    >
      <ResponsiveContainer width="100%" height={chartHeight} minWidth={0} minHeight={chartHeight}>
        <AreaChart
          data={data}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={`gradient-${title}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={primaryColor} stopOpacity={0.8} />
              <stop offset="95%" stopColor={primaryColor} stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.2)" />
          <XAxis
            dataKey="date"
            tickFormatter={formatChartDate}
            stroke="#94a3b8"
            style={{ fontSize: '12px' }}
          />
          <YAxis
            tickFormatter={(value) => formatValue(value)}
            stroke="#94a3b8"
            style={{ fontSize: '12px' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(30, 41, 59, 0.95)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: '8px',
              color: '#e2e8f0',
            }}
            labelFormatter={(label) => `${t('chart.dateLabel')}: ${formatChartDate(label)}`}
            formatter={(value: unknown) => {
              if (value === undefined) return [fallback, title];
              return [formatValue(value), title];
            }}
          />
          <Legend
            wrapperStyle={{ color: '#94a3b8', fontSize: '12px' }}
            iconType="line"
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={primaryColor}
            strokeWidth={2}
            fill={`url(#gradient-${title})`}
            name={title}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
