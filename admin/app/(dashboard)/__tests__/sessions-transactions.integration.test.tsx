import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ActiveSessionsPage from '../sessions/page';
import TransactionsPage from '../transactions/page';
import { ApiRequestError, apiPost } from '@/lib/api';
import type { ChargingRecord, PaginatedResponse } from '@/types';

const internalUuid = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const missingIdentityUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';
const mutate = vi.fn();
const testState = { canControl: true };
const activeSessions = [{
  id: 'session-1',
  site: { id: 'SITE-01', name: 'Centro', address: 'Calle 1' },
  charger: { id: internalUuid, display_code: 'CP001', display_name: 'Lobby' },
  connector: { id: 'connector-1', connector_number: 1, physical_reference: 'CP001-1' },
  user_reference: 'USR-***1',
  start_time: '2026-07-18T15:30:45Z',
  energy_kwh: 0,
  power_kw: undefined,
  duration_minutes: 0,
  last_meter_at: '2026-07-18T15:35:45Z',
  estimated_cost: null,
  currency: null,
  status: 'ongoing',
}];
const chargingRecords: PaginatedResponse<ChargingRecord> = {
  items: [{
    id: missingIdentityUuid,
    record_number: 'CHG-20260718-0101',
    invoice_number: 'INV-20260718-0001',
    ocpp_transaction_id: 101,
    site: { site_code: 'SITE-01', name: 'Centro', address: 'Calle 1' },
    charger: { display_code: 'CP001', display_name: 'Lobby', ocpp_identity: 'CO.BOGOTA:CP-01' },
    connector: {
      evse_id: 1,
      physical_reference: 'CP001-1',
      connector_type: 'Type 2',
      max_power_kw: '7.00',
    },
    user_reference: 'USR-***1',
    start_time: '2026-07-18T15:30:45Z',
    end_time: '2026-07-18T16:30:45Z',
    energy_kwh: '2.660',
    duration_minutes: '60.00',
    amount: '2700.00',
    currency: 'COP',
    status: 'completed',
    payment_status: 'paid',
    anomaly_codes: ['power_exceeds_rating'],
  }],
  total: 1,
  limit: 50,
  offset: 0,
};

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: testState.canControl ? ['chargers.control'] : [] }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('swr', () => ({
  default: (key: string) => ({
    data: key.endsWith('/active')
      ? activeSessions
      : key === '/api/v1/sites'
        ? []
        : key.startsWith('/api/v1/transactions?')
          ? chargingRecords
          : undefined,
    error: null,
    isLoading: false,
    mutate,
  }),
}));

describe('INT-001 admin session and transaction presentation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    testState.canControl = true;
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
  });

  it('shows business-facing charging record fields without internal UUIDs', () => {
    const { container } = render(<TransactionsPage />);

    expect(screen.getByText('INV-20260718-0001')).toBeInTheDocument();
    expect(screen.getByText('CHG-20260718-0101')).toBeInTheDocument();
    expect(screen.getByText('Centro')).toBeInTheDocument();
    expect(screen.getByText(/CP001 · Lobby · CP001-1 · Type 2 · 7\.00 kW/)).toBeInTheDocument();
    expect(screen.getByText('USR-***1')).toBeInTheDocument();
    expect(screen.getByText(/COP/)).toHaveTextContent('2,700.00');
    expect(screen.getByText('平均功率明显超过枪口额定功率')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(container).not.toHaveTextContent(internalUuid);
    expect(container).not.toHaveTextContent(missingIdentityUuid);
  });

  it('prioritizes operational session fields and marks unavailable cost', () => {
    const { container } = render(<ActiveSessionsPage />);

    expect(screen.getByText('Centro')).toBeInTheDocument();
    expect(screen.getByText('CP001')).toBeInTheDocument();
    expect(screen.getByText('CP001-1')).toBeInTheDocument();
    expect(screen.getByText('USR-***1')).toBeInTheDocument();
    expect(screen.getByText('暂不可用')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /查看充电桩/ })).toHaveAttribute('href', `/chargers/${internalUuid}`);
    expect(screen.getAllByText(/进行中/).length).toBeGreaterThan(0);
    expect(screen.getByText('未提供')).toBeInTheDocument();
    expect(container).not.toHaveTextContent(internalUuid);
    expect(container).toHaveTextContent('0.00 kWh');
  });

  it('hides remote stop without chargers.control', () => {
    testState.canControl = false;
    render(<ActiveSessionsPage />);
    expect(screen.queryByTestId('session-remote-stop')).not.toBeInTheDocument();
  });

  it('shows session information and does not send when the remote-stop dialog is cancelled', async () => {
    const user = userEvent.setup();
    render(<ActiveSessionsPage />);

    await user.click(screen.getByTestId('session-remote-stop'));

    const dialog = screen.getByRole('dialog', { name: '远程停止确认' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText('Centro')).toBeInTheDocument();
    expect(within(dialog).getByText('Lobby')).toBeInTheDocument();
    expect(within(dialog).getByText('CP001-1')).toBeInTheDocument();
    expect(within(dialog).queryByText('101')).not.toBeInTheDocument();
    await user.type(screen.getByTestId('remote-stop-reason'), 'Driver requested support');
    await user.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog', { name: '远程停止确认' })).not.toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it('sends the selected row payload with an idempotency key and refreshes', async () => {
    const user = userEvent.setup();
    vi.mocked(apiPost).mockResolvedValueOnce({ success: true });
    render(<ActiveSessionsPage />);

    await user.click(screen.getByTestId('session-remote-stop'));
    const confirm = screen.getByTestId('remote-stop-confirm');
    expect(confirm).toBeDisabled();
    await user.type(screen.getByTestId('remote-stop-reason'), '  Driver requested support  ');
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/ocpp/remote-stop-session',
      {
        session_id: 'session-1',
        operation_reason: 'Driver requested support',
      },
      { headers: { 'Idempotency-Key': expect.any(String) } }
    ));
    expect(window.alert).toHaveBeenCalledWith('远程停止已被充电桩接受');
    expect(mutate).toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: '远程停止确认' })).not.toBeInTheDocument();
  });

  it('distinguishes rejection and offline feedback', async () => {
    const user = userEvent.setup();
    vi.mocked(apiPost)
      .mockResolvedValueOnce({ success: false })
      .mockRejectedValueOnce(new ApiRequestError('offline', 503));
    const { unmount } = render(<ActiveSessionsPage />);
    await user.click(screen.getByTestId('session-remote-stop'));
    await user.type(screen.getByTestId('remote-stop-reason'), 'Driver requested support');
    await user.click(screen.getByTestId('remote-stop-confirm'));
    await waitFor(() => expect(window.alert).toHaveBeenCalledWith('远程停止被充电桩拒绝'));
    unmount();

    render(<ActiveSessionsPage />);
    await user.click(screen.getByTestId('session-remote-stop'));
    await user.type(screen.getByTestId('remote-stop-reason'), 'Driver requested support');
    await user.click(screen.getByTestId('remote-stop-confirm'));
    await waitFor(() => expect(window.alert).toHaveBeenCalledWith('充电桩离线，无法远程停止'));
  });
});
