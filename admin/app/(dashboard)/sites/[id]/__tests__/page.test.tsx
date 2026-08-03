import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiteDetailPage from '../page';
import { apiDelete, apiGet, apiPost } from '@/lib/api';

const siteId = 'site-uuid-1';
const siteMutate = vi.fn();
const testState = vi.hoisted(() => ({
  lifecycleStatus: 'active' as 'active' | 'archived',
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: testState.push }),
  useParams: () => ({ id: siteId }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: ['sites.write', 'tariffs.edit'] }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('@/components/map/GoogleMapView', () => ({
  default: () => <div data-testid="site-map" />,
}));

vi.mock('@/components/sites/AddressAutocomplete', () => ({
  default: () => <div data-testid="site-address" />,
}));

vi.mock('swr', () => ({
  default: (key: string | null) => {
    if (key === `/api/v1/sites/${siteId}`) {
      const archived = testState.lifecycleStatus === 'archived';
      return {
        data: {
          id: siteId,
          site_code: 'SITE-CENTRO',
          name: 'Centro',
          address: 'Calle 1',
          latitude: 4.61,
          longitude: -74.08,
          is_active: !archived,
          lifecycle_status: testState.lifecycleStatus,
          archived_at: archived ? '2026-08-02T12:00:00Z' : null,
          archive_reason: archived ? 'Location contract ended' : null,
          active_charge_points_count: archived ? 0 : 1,
          retiring_charge_points_count: 0,
          retired_charge_points_count: 2,
          price_per_kwh: 1200,
          charge_points: archived ? [] : [{
            id: 'charger-uuid-1',
            ocpp_identity: 'CO.BOGOTA:CP-01',
            display_code: 'A01',
            display_name: 'Lobby charger',
            status: 'Available',
            site_id: siteId,
            lifecycle_status: 'active',
          }],
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-08-02T00:00:00Z',
        },
        error: null,
        isLoading: false,
        mutate: siteMutate,
      };
    }
    return { data: undefined, error: null, isLoading: false, mutate: vi.fn() };
  },
}));

describe('site detail lifecycle', () => {
  beforeEach(() => {
    testState.lifecycleStatus = 'active';
    vi.clearAllMocks();
  });

  it('shows archive blockers and opens the relevant charger', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockResolvedValueOnce({
      site_id: siteId,
      lifecycle_status: 'active',
      can_archive_now: false,
      counts: {
        active_charge_points: 1,
        retiring_charge_points: 0,
        retired_charge_points: 2,
        ongoing_sessions: 0,
        unsettled_business_records: 0,
      },
      blockers: [{
        type: 'active_charge_point',
        resource_id: 'charger-uuid-1',
        display_code: 'A01',
      }],
    });

    render(<SiteDetailPage />);
    await user.click(screen.getByTestId('admin-site-archive'));

    expect(await screen.findByTestId('site-archive-blockers')).toHaveTextContent('A01');
    expect(screen.getByText('退役充电桩不阻止归档，但会保留在资产归档中并阻止永久删除。')).toBeInTheDocument();
    await user.type(screen.getByTestId('site-lifecycle-reason'), 'Location contract ended');
    expect(screen.getByTestId('site-lifecycle-confirm')).toBeDisabled();

    await user.click(screen.getByTestId('site-blocker-open-charger-uuid-1'));
    expect(testState.push).toHaveBeenCalledWith('/chargers/charger-uuid-1');
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('shows a visible error and disables confirmation when archive preflight fails', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('site archive preflight unavailable'));

    render(<SiteDetailPage />);
    await user.click(screen.getByTestId('admin-site-archive'));

    expect(await screen.findByRole('alert')).toHaveTextContent('site archive preflight unavailable');
    await user.type(screen.getByTestId('site-lifecycle-reason'), 'Location contract ended');
    expect(screen.getByTestId('site-lifecycle-confirm')).toBeDisabled();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('archives a site after preflight passes', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockResolvedValueOnce({
      site_id: siteId,
      lifecycle_status: 'active',
      can_archive_now: true,
      counts: {
        active_charge_points: 0,
        retiring_charge_points: 0,
        retired_charge_points: 2,
        ongoing_sessions: 0,
        unsettled_business_records: 0,
      },
      blockers: [],
    });
    vi.mocked(apiPost).mockResolvedValueOnce({ lifecycle_status: 'archived' });

    render(<SiteDetailPage />);
    await user.click(screen.getByTestId('admin-site-archive'));
    await screen.findAllByText('正常充电桩');
    await user.type(screen.getByTestId('site-lifecycle-reason'), '  Location contract ended  ');
    await user.click(screen.getByTestId('site-lifecycle-confirm'));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      `/api/v1/sites/${siteId}/archive`,
      { reason: 'Location contract ended' }
    ));
    expect(siteMutate).toHaveBeenCalled();
  });

  it('makes an archived site read-only and restores only the site', async () => {
    testState.lifecycleStatus = 'archived';
    const user = userEvent.setup();
    vi.mocked(apiPost).mockResolvedValueOnce({ lifecycle_status: 'active' });

    render(<SiteDetailPage />);
    expect(screen.getByText('已归档')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '编辑' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '添加充电桩' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '绑定充电桩' })).toBeDisabled();
    expect(screen.getByText('Location contract ended')).toBeInTheDocument();

    await user.click(screen.getByTestId('admin-site-restore'));
    expect(screen.getByText('恢复后站点重新进入运营列表，但站点下的退役充电桩仍保持退役。')).toBeInTheDocument();
    await user.type(screen.getByTestId('site-lifecycle-reason'), 'Location reopened');
    await user.click(screen.getByTestId('site-lifecycle-confirm'));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      `/api/v1/sites/${siteId}/restore`,
      { reason: 'Location reopened' }
    ));
  });

  it('requires the exact site code before permanent deletion', async () => {
    const user = userEvent.setup();
    vi.mocked(apiDelete).mockResolvedValueOnce({ success: true });

    render(<SiteDetailPage />);
    await user.click(screen.getByTestId('admin-site-delete'));
    await user.type(screen.getByTestId('site-lifecycle-reason'), 'Created by mistake');
    await user.type(screen.getByTestId('site-delete-confirmation'), 'WRONG');
    expect(screen.getByTestId('site-lifecycle-confirm')).toBeDisabled();

    await user.clear(screen.getByTestId('site-delete-confirmation'));
    await user.type(screen.getByTestId('site-delete-confirmation'), 'SITE-CENTRO');
    await user.click(screen.getByTestId('site-lifecycle-confirm'));

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith(
      `/api/v1/sites/${siteId}`,
      { confirmation: 'SITE-CENTRO', reason: 'Created by mistake' }
    ));
    expect(testState.push).toHaveBeenCalledWith('/sites');
  });
});
