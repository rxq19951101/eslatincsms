import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PaymentsPage from '../page';
import { useAuthStore } from '@/store/authStore';

vi.mock('swr', () => ({
  default: () => ({
    data: [{
      id: 'payment-1',
      app_user_id: 'user-1',
      user_email: null,
      type: 'top_up',
      amount: 10000,
      currency: 'COP',
      reference: null,
      external_reference: 'MP-ORDER-1',
      status: 'created',
      created_at: '2026-07-21T00:00:00Z',
    }],
    error: null,
    isLoading: false,
    mutate: vi.fn(),
  }),
}));

describe('Payments nullable API contract', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: 'admin-1',
        username: 'admin',
        email: 'admin@example.test',
        is_super_admin: true,
        tenant_list: [],
      },
    });
  });

  it('renders and filters an order with a null Wompi reference', () => {
    render(<PaymentsPage />);
    expect(screen.getByText('MP-ORDER-1')).toBeInTheDocument();
    expect(screen.getByText(/未提供/)).toBeInTheDocument();
  });
});
