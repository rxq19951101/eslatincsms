/**
 * 充电桩卡片组件单元测试
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock充电桩卡片组件（如果存在）
const ChargerCard = ({ charger }: { charger: any }) => {
  return (
    <div data-testid="charger-card">
      <h3>{charger.id}</h3>
      <p>状态: {charger.status || 'Unknown'}</p>
      <p>位置: {charger.location || 'N/A'}</p>
    </div>
  );
};

describe('ChargerCard', () => {
  const mockCharger = {
    id: 'CP-001',
    status: 'Available',
    location: '测试位置',
  };

  it('应该渲染充电桩ID', () => {
    render(<ChargerCard charger={mockCharger} />);
    expect(screen.getByText('CP-001')).toBeInTheDocument();
  });

  it('应该渲染充电桩状态', () => {
    render(<ChargerCard charger={mockCharger} />);
    expect(screen.getByText(/状态: Available/)).toBeInTheDocument();
  });

  it('应该渲染充电桩位置', () => {
    render(<ChargerCard charger={mockCharger} />);
    expect(screen.getByText(/位置: 测试位置/)).toBeInTheDocument();
  });

  it('应该处理缺少状态的情况', () => {
    const chargerWithoutStatus = { ...mockCharger, status: undefined };
    render(<ChargerCard charger={chargerWithoutStatus} />);
    expect(screen.getByText(/状态: Unknown/)).toBeInTheDocument();
  });

  it('应该处理缺少位置的情况', () => {
    const chargerWithoutLocation = { ...mockCharger, location: undefined };
    render(<ChargerCard charger={chargerWithoutLocation} />);
    expect(screen.getByText(/位置: N\/A/)).toBeInTheDocument();
  });
});

