import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ChargerDetailPage from '../page';
import { apiDelete, apiGet, apiPost } from '@/lib/api';

const chargerId = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const chargerMutate = vi.fn();
const sessionsMutate = vi.fn();
const testState = vi.hoisted(() => ({
  lifecycleStatus: 'active' as 'active' | 'retired',
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ back: vi.fn(), push: testState.push }),
  useParams: () => ({ id: chargerId }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: ['chargers.control', 'chargers.write'] }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('swr', () => ({
  default: (key: string | null) => {
    if (key === `/api/v1/chargers/${chargerId}`) {
      return {
        data: {
          id: chargerId,
          ocpp_identity: 'CO.BOGOTA:CP-01',
          display_code: 'CP001',
          display_name: 'Lobby charger',
          location_hint: 'Basement A',
          site: { id: 'SITE-01', site_code: 'CENTRO', name: 'Centro', address: 'Calle 1' },
          status: 'Available',
          lifecycle_status: testState.lifecycleStatus,
          retirement_reason: testState.lifecycleStatus === 'retired' ? 'Physical charger removed' : null,
          retired_at: testState.lifecycleStatus === 'retired' ? '2026-08-02T12:00:00Z' : null,
          original_site: testState.lifecycleStatus === 'retired'
            ? { id: 'SITE-01', site_code: 'CENTRO', name: 'Centro' }
            : null,
          is_configured: true,
          has_location: true,
          has_pricing: true,
          pricing: {
            pricing_mode: 'free',
            pricing_source: 'charger',
            tariff_id: 'tariff-charger-1',
            base_price_per_kwh: '0.00',
            service_fee: '0.00',
            currency: 'COP',
            free_reason: 'Fleet launch promotion',
            valid_from: '2026-08-01T00:00:00Z',
            valid_until: '2099-12-31T23:59:00Z',
          },
          evses: [{
            evse_id: 2,
            connector_type: 'Type2',
            status: 'Available',
          }],
        },
        error: null,
        isLoading: false,
        mutate: chargerMutate,
      };
    }
    if (key === '/api/v1/transactions/active') {
      return {
        data: [{
          id: 'session-2',
          site: { id: 'SITE-01', name: 'Centro', address: 'Calle 1' },
          charger: { id: chargerId, display_code: 'CP001', display_name: 'Lobby' },
          connector: { id: 'connector-2', connector_number: 2, physical_reference: null },
          start_time: '2026-07-18T15:30:45Z',
          status: 'ongoing',
        }],
        error: null,
        isLoading: false,
        mutate: sessionsMutate,
      };
    }
    if (key?.startsWith('/api/v1/transactions?')) {
      return {
        data: { items: [], total: 0, limit: 10, offset: 0 },
        error: null,
        isLoading: false,
        mutate: vi.fn(),
      };
    }
    return {
      data: key?.includes('/qr') ? { qr_codes: [] } : undefined,
      error: null,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
}));

describe('charger detail remote stop', () => {
  beforeEach(() => {
    testState.lifecycleStatus = 'active';
    vi.clearAllMocks();
  });

  it('uses public charger labels and keeps the OCPP identity in commissioning only', async () => {
    const user = userEvent.setup();
    render(<ChargerDetailPage />);

    expect(screen.getByRole('heading', { name: 'Lobby charger' })).toBeInTheDocument();
    expect(screen.getByText('CP001')).toBeInTheDocument();
    expect(screen.getByText('Centro')).toBeInTheDocument();
    expect(screen.queryByText('CO.BOGOTA:CP-01')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: '调试与投运' }));
    expect(screen.getByText('OCPP 技术身份')).toBeInTheDocument();
    expect(screen.getByText('CO.BOGOTA:CP-01')).toBeInTheDocument();
  });

  it('shows free charger pricing metadata in COP and never uses the yen symbol', () => {
    const { container } = render(<ChargerDetailPage />);

    const summary = screen.getByTestId('pricing-summary');
    expect(summary).toHaveTextContent('免费');
    expect(summary).toHaveTextContent('充电桩覆盖');
    expect(summary).toHaveTextContent('Fleet launch promotion');
    expect(summary).toHaveTextContent('COP');
    expect(container).not.toHaveTextContent('¥');
  });

  it('uses the localized connector fallback and submits only the session ID', async () => {
    const user = userEvent.setup();
    vi.mocked(apiPost).mockResolvedValueOnce({ success: true });
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<ChargerDetailPage />);
    await user.click(screen.getByRole('tab', { name: '远程控制' }));
    expect(screen.getAllByText('充电枪 2').length).toBeGreaterThan(0);

    await user.click(screen.getByTestId('admin-remote-stop'));
    const dialog = screen.getByRole('dialog', { name: '远程停止确认' });
    expect(within(dialog).getByText('充电枪 2')).toBeInTheDocument();
    expect(within(dialog).queryByText('CO.BOGOTA:CP-01')).not.toBeInTheDocument();

    await user.type(screen.getByTestId('remote-stop-reason'), '  Driver requested support  ');
    await user.click(screen.getByTestId('remote-stop-confirm'));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/ocpp/remote-stop-session',
      {
        session_id: 'session-2',
        operation_reason: 'Driver requested support',
      },
      { headers: { 'Idempotency-Key': expect.any(String) } }
    ));
    expect(sessionsMutate).toHaveBeenCalled();
  });

  it('shows retirement blockers and prevents retirement while preflight fails', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockResolvedValueOnce({
      charge_point_id: chargerId,
      lifecycle_status: 'active',
      can_retire_now: false,
      will_wait_for_sessions: false,
      counts: {
        ongoing_sessions: 1,
        pending_remote_commands: 0,
        unsettled_business_records: 0,
      },
      blockers: [{ type: 'ongoing_session', resource_id: 'session-2' }],
    });

    render(<ChargerDetailPage />);
    await user.click(screen.getByTestId('admin-charger-retire'));

    expect(await screen.findByTestId('charger-retirement-blockers')).toHaveTextContent('session-2');
    await user.type(screen.getByTestId('charger-lifecycle-reason'), 'Physical charger removed');
    expect(screen.getByTestId('charger-lifecycle-confirm')).toBeDisabled();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('retires a charger after a successful preflight', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockResolvedValueOnce({
      charge_point_id: chargerId,
      lifecycle_status: 'active',
      can_retire_now: true,
      will_wait_for_sessions: false,
      counts: {
        ongoing_sessions: 0,
        pending_remote_commands: 0,
        unsettled_business_records: 0,
      },
      blockers: [],
    });
    vi.mocked(apiPost).mockResolvedValueOnce({ lifecycle_status: 'retired' });

    render(<ChargerDetailPage />);
    await user.click(screen.getByTestId('admin-charger-retire'));
    await screen.findByText('进行中会话');
    await user.type(screen.getByTestId('charger-lifecycle-reason'), '  Physical charger removed  ');
    await user.click(screen.getByTestId('charger-lifecycle-confirm'));

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      `/api/v1/chargers/${chargerId}/retire`,
      { reason: 'Physical charger removed' }
    ));
    expect(chargerMutate).toHaveBeenCalled();
  });

  it('keeps the dialog open and shows the API error when retirement fails', async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockResolvedValueOnce({
      charge_point_id: chargerId,
      lifecycle_status: 'active',
      can_retire_now: true,
      will_wait_for_sessions: false,
      counts: {
        ongoing_sessions: 0,
        pending_remote_commands: 0,
        unsettled_business_records: 0,
      },
      blockers: [],
    });
    vi.mocked(apiPost).mockRejectedValueOnce(
      new Error('charger_retirement_blocked: unsettled business')
    );

    render(<ChargerDetailPage />);
    await user.click(screen.getByTestId('admin-charger-retire'));
    await screen.findByText('进行中会话');
    await user.type(screen.getByTestId('charger-lifecycle-reason'), 'Physical charger removed');
    await user.click(screen.getByTestId('charger-lifecycle-confirm'));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'charger_retirement_blocked: unsettled business'
    );
    expect(screen.getByTestId('charger-lifecycle-dialog')).toBeInTheDocument();
    expect(chargerMutate).not.toHaveBeenCalled();
  });

  it('hides operational controls for retired chargers and shows the one-time secret after restore', async () => {
    testState.lifecycleStatus = 'retired';
    const user = userEvent.setup();
    vi.mocked(apiPost).mockResolvedValueOnce({
      lifecycle_status: 'active',
      commissioning_status: 'testing',
      ocpp_identity: 'CO.BOGOTA:CP-01',
      ocpp_secret: 'new-secret-once',
      credential_rotated: true,
    });

    render(<ChargerDetailPage />);
    expect(screen.queryByRole('tab', { name: '远程控制' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '二维码' })).not.toBeInTheDocument();
    expect(screen.getByText('已退役')).toBeInTheDocument();

    await user.click(screen.getByTestId('admin-charger-restore'));
    await user.type(screen.getByTestId('charger-lifecycle-reason'), 'Device returned to service');
    await user.click(screen.getByTestId('charger-lifecycle-confirm'));

    expect(await screen.findByTestId('charger-restored-secret')).toHaveTextContent('new-secret-once');
  });

  it('requires the exact OCPP identity before permanent deletion', async () => {
    const user = userEvent.setup();
    vi.mocked(apiDelete).mockResolvedValueOnce({ success: true });

    render(<ChargerDetailPage />);
    await user.click(screen.getByTestId('admin-charger-delete'));
    await user.type(screen.getByTestId('charger-lifecycle-reason'), 'Created by mistake');
    await user.type(screen.getByTestId('charger-delete-confirmation'), 'WRONG');
    expect(screen.getByTestId('charger-lifecycle-confirm')).toBeDisabled();

    await user.clear(screen.getByTestId('charger-delete-confirmation'));
    await user.type(screen.getByTestId('charger-delete-confirmation'), 'CO.BOGOTA:CP-01');
    await user.click(screen.getByTestId('charger-lifecycle-confirm'));

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith(
      `/api/v1/chargers/${chargerId}`,
      {
        confirmation: 'CO.BOGOTA:CP-01',
        reason: 'Created by mistake',
      }
    ));
    expect(testState.push).toHaveBeenCalledWith('/chargers');
  });
});
