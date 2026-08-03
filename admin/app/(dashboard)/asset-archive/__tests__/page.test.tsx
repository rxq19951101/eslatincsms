import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AssetArchivePage from '../page';

const testState = vi.hoisted(() => ({
  permissions: ['sites.read', 'chargers.read'] as string[],
  push: vi.fn(),
  keys: [] as string[],
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: testState.push }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: testState.permissions, isLoading: false }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: vi.fn(),
}));

vi.mock('swr', () => ({
  default: (key: string | null) => {
    if (key) testState.keys.push(key);
    if (key?.startsWith('/api/v1/asset-archive/sites?')) {
      return {
        data: [{
          id: 'site-1',
          site_code: 'SITE-CENTRO',
          name: 'Centro archived',
          address: 'Calle 1',
          lifecycle_status: 'archived',
          archived_at: '2026-08-02T12:00:00Z',
          archive_reason: 'Location contract ended',
          archived_by: { id: 'admin-1', username: 'operator-one', full_name: null },
          active_charge_points_count: 0,
          retiring_charge_points_count: 0,
          retired_charge_points_count: 2,
        }],
        error: null,
        isLoading: false,
      };
    }
    if (key?.startsWith('/api/v1/asset-archive/chargers?')) {
      return {
        data: [{
          id: 'charger-1',
          ocpp_identity: 'CO.BOGOTA:CP-01',
          display_code: 'A01',
          display_name: 'Lobby charger',
          vendor: 'Vendor',
          model: 'Model',
          lifecycle_status: 'retired',
          retirement_reason: 'Physical charger removed',
          retired_at: '2026-08-02T11:00:00Z',
          retired_by: { id: 'admin-1', username: 'operator-one', full_name: 'Operator One' },
          original_site: { id: 'site-1', site_code: 'SITE-CENTRO', name: 'Centro archived' },
        }],
        error: null,
        isLoading: false,
      };
    }
    if (key?.startsWith('/api/v1/sites?')) {
      return {
        data: [{ id: 'site-1', site_code: 'SITE-CENTRO', name: 'Centro archived' }],
        error: null,
        isLoading: false,
      };
    }
    return { data: undefined, error: null, isLoading: false };
  },
}));

describe('asset archive page', () => {
  beforeEach(() => {
    testState.permissions = ['sites.read', 'chargers.read'];
    testState.keys.length = 0;
    vi.clearAllMocks();
  });

  it('shows archived sites and opens their retained detail', async () => {
    const user = userEvent.setup();
    render(<AssetArchivePage />);

    expect(screen.getByRole('heading', { name: '资产归档' })).toBeInTheDocument();
    expect(screen.getByText('Centro archived')).toBeInTheDocument();
    expect(screen.getByText('Location contract ended')).toBeInTheDocument();
    expect(screen.getByText('operator-one')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '查看详情' }));
    expect(testState.push).toHaveBeenCalledWith('/sites/site-1');
  });

  it('shows retired chargers and links to detail and charging history', async () => {
    const user = userEvent.setup();
    render(<AssetArchivePage />);
    await user.click(screen.getByRole('tab', { name: '已退役充电桩' }));

    expect(screen.getByText('Lobby charger')).toBeInTheDocument();
    expect(screen.getByText(/CO\.BOGOTA:CP-01/)).toBeInTheDocument();
    expect(screen.getByText('Physical charger removed')).toBeInTheDocument();
    expect(screen.getByText('Operator One')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '查看详情' }));
    expect(testState.push).toHaveBeenCalledWith('/chargers/charger-1');
    await user.click(screen.getByRole('button', { name: '历史充电记录' }));
    expect(testState.push).toHaveBeenCalledWith('/transactions?charge_point_id=CO.BOGOTA%3ACP-01');
  });

  it('applies search and UTC date boundaries to both archive queries', async () => {
    const user = userEvent.setup();
    render(<AssetArchivePage />);

    await user.type(screen.getByTestId('archive-search'), ' contract ended ');
    await user.type(screen.getByTestId('archive-from'), '2026-08-01');
    await user.type(screen.getByTestId('archive-to'), '2026-08-03');
    await user.click(screen.getByTestId('archive-apply'));

    await waitFor(() => {
      expect(testState.keys.some((key) => key.includes(
        'search=contract+ended'
      ) && key.includes(
        'archived_from=2026-08-01T00%3A00%3A00.000Z'
      ) && key.includes(
        'archived_to=2026-08-03T23%3A59%3A59.999Z'
      ))).toBe(true);
      expect(testState.keys.some((key) => key.includes(
        'retired_from=2026-08-01T00%3A00%3A00.000Z'
      ) && key.includes(
        'retired_to=2026-08-03T23%3A59%3A59.999Z'
      ))).toBe(true);
    });
  });

  it('falls back to the charger archive for a charger-only operator', () => {
    testState.permissions = ['chargers.read'];
    render(<AssetArchivePage />);

    expect(screen.queryByRole('tab', { name: '已归档站点' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '已退役充电桩' })).toBeInTheDocument();
    expect(screen.getByText('Lobby charger')).toBeInTheDocument();
  });
});
