import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ActiveSessionsPage from '../sessions/page';
import TransactionsPage from '../transactions/page';

const internalUuid = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const missingIdentityUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

vi.mock('swr', () => ({
  default: (key: string) => ({
    data: key.endsWith('/active')
      ? [{
          id: 'session-1',
          transaction_id: 101,
          charge_point_id: internalUuid,
          ocpp_identity: 'CO.BOGOTA:CP-01',
          start_time: '2026-07-18T15:30:45Z',
          energy_kwh: 0,
          power_kw: undefined,
          duration_minutes: 0,
          status: 'ongoing',
        }]
      : [
          {
            id: 'transaction-1',
            transaction_id: 101,
            charge_point_id: internalUuid,
            ocpp_identity: 'CO.BOGOTA:CP-01',
            id_tag: 'USER-1',
            start_time: '2026-07-18T15:30:45Z',
            end_time: '2026-07-18T16:30:45Z',
            energy_kwh: 0,
            duration_minutes: 0,
            status: 'completed',
          },
          {
            id: 'transaction-2',
            transaction_id: 102,
            charge_point_id: missingIdentityUuid,
            id_tag: 'USER-2',
            start_time: '2026-07-18T16:30:45Z',
            status: 'ongoing',
          },
        ],
    error: null,
    isLoading: false,
    mutate: vi.fn(),
  }),
}));

describe('INT-001 admin session and transaction presentation', () => {
  it('shows the public OCPP identity in transactions without a UUID fallback', () => {
    const { container } = render(<TransactionsPage />);

    const identities = screen.getAllByTestId('transaction-ocpp-identity');
    expect(identities[0]).toHaveTextContent('CO.BOGOTA:CP-01');
    expect(identities[1]).toHaveTextContent('未提供');
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(container).not.toHaveTextContent(internalUuid);
    expect(container).not.toHaveTextContent(missingIdentityUuid);
    expect(container).toHaveTextContent('0.00');
    expect(container).toHaveTextContent('0.0');
  });

  it('shows the public OCPP identity and localized state/default in active sessions', () => {
    const { container } = render(<ActiveSessionsPage />);

    expect(screen.getByTestId('session-ocpp-identity')).toHaveTextContent('CO.BOGOTA:CP-01');
    expect(screen.getAllByText(/进行中/).length).toBeGreaterThan(0);
    expect(screen.getByText('未提供')).toBeInTheDocument();
    expect(container).not.toHaveTextContent(internalUuid);
    expect(container).toHaveTextContent('0.00 kWh');
  });
});
