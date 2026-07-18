import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChargersPage from '../page';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('ChargersPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('显示充电桩管理已迁移到站点管理', () => {
    render(<ChargersPage />);
    expect(screen.getByText('该模块已迁移：请以站点为单位进行管理')).toBeInTheDocument();
    expect(screen.getByText('迁移说明')).toBeInTheDocument();
  });

  it('可以跳转到站点管理', async () => {
    const user = userEvent.setup();
    render(<ChargersPage />);
    await user.click(screen.getByRole('button', { name: /前往站点管理/i }));
    expect(mockPush).toHaveBeenCalledWith('/sites');
  });
});
