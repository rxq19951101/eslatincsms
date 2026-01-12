'use client';

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { TrendDataPoint } from '@/types';

interface TrendChartProps {
  data: TrendDataPoint[];
  title: string;
  color: string;
  unit?: string;
}

export function TrendChart({ data, title, color, unit = '' }: TrendChartProps) {
  // 格式化日期显示
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  // 格式化数值显示
  const formatValue = (value: number) => {
    if (unit === '¥') {
      return `¥${value.toFixed(2)}`;
    }
    if (unit === 'kWh') {
      return `${value.toFixed(2)} kWh`;
    }
    return value.toFixed(0);
  };

  // 从 CSS variable 获取颜色
  const primaryColor = color || 'hsl(var(--chart-primary))';
  const secondaryColor = 'hsl(var(--chart-secondary))';

  return (
    // Recharts 的 ResponsiveContainer 需要父容器有明确高度，否则会出现 width/height=-1
    <div className="w-full h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
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
            tickFormatter={formatDate}
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
            labelFormatter={(label) => `日期: ${label}`}
            formatter={(value: number | undefined) => {
              if (value === undefined) return ['N/A', title];
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