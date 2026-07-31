import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ChargerDetailPage from '../page';
import { apiPost } from '@/lib/api';

const chargerId = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const chargerMutate = vi.fn();
const sessionsMutate = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
  useParams: () => ({ id: chargerId }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: ['chargers.control'] }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
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
          is_configured: true,
          has_location: true,
          has_pricing: true,
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
});
