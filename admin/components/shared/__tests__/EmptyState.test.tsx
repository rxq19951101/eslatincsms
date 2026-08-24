import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from '../EmptyState';
import { Zap } from 'lucide-react';

describe('EmptyState Component', () => {
  it('应该渲染默认标题', () => {
    render(<EmptyState />);
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });

  it('应该渲染自定义标题和描述', () => {
    render(
      <EmptyState
        title="没有找到数据"
        description="请尝试调整筛选条件"
      />
    );
    expect(screen.getByText('没有找到数据')).toBeInTheDocument();
    expect(screen.getByText('请尝试调整筛选条件')).toBeInTheDocument();
  });

  it('应该渲染图标', () => {
    const { container } = render(<EmptyState icon={Zap} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });
});