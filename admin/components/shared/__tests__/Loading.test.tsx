import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Loading } from '../Loading';

describe('Loading Component', () => {
  it('应该渲染默认加载消息', () => {
    render(<Loading />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('应该渲染自定义加载消息', () => {
    render(<Loading message="正在处理..." />);
    expect(screen.getByText('正在处理...')).toBeInTheDocument();
  });

  it('应该显示加载动画', () => {
    const { container } = render(<Loading />);
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });
});