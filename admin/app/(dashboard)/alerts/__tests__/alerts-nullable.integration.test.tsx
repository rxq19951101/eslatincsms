import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import AlertsPage from '../page';

const testState = vi.hoisted(() => ({
  locale: 'zh-CN' as 'zh-CN' | 'en' | 'es',
  alerts: [] as Array<Record<string, unknown>>,
  canWriteAlerts: false,
}));
const apiPut = vi.hoisted(() => vi.fn().mockResolvedValue({}));

vi.mock('swr', () => ({
  default: () => ({
    data: testState.alerts,
    error: null,
    isLoading: false,
    mutate: vi.fn(),
  }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPut,
}));

vi.mock('@/lib/i18n', () => ({
  useI18n: () => ({
    locale: testState.locale,
    setLocale: vi.fn(),
    t: (key: string) => key,
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: testState.canWriteAlerts ? ['alerts.write'] : [] }),
  hasPermission: (permissions: string[], required: string) => permissions.includes(required),
}));

const structuredAlert = {
  id: '11111111-1111-4111-8111-111111111111',
  tenant_id: '22222222-2222-4222-8222-222222222222',
  charge_point_id: '33333333-3333-4333-8333-333333333333',
  evse_id: '44444444-4444-4444-8444-444444444444',
  alert_type: 'charger_offline',
  alert_code: 'charger.offline.heartbeat_timeout',
  message_params: {
    timeout_seconds: 90,
    tenant_id: 'param-tenant-internal-uuid',
    nested: {
      event_id: 'param-event-internal-uuid',
      reason: 'heartbeat_timeout',
    },
  },
  raw_message: 'OCPP WebSocket connection closed',
  severity: 'critical',
  status: 'pending',
  title: 'Charger SIM-E2E-CP-001 offline',
  description: 'Charger has not sent a heartbeat for 90 seconds',
  metadata: {},
  site: {
    site_code: 'site_0123456789abcdef',
    name: 'SIM E2E Test Site',
    address: 'Calle 100 # 10-20, Bogota',
  },
  charge_point: {
    ocpp_identity: 'SIM-E2E-CP-001',
    model: 'Simulated 7kW',
    serial_number: 'SIM-001',
  },
  evse: { evse_id: 1, physical_reference: 'Bay 1' },
  created_at: '2026-07-21T00:00:00Z',
  updated_at: '2026-07-21T00:00:00Z',
};

describe('Alerts structured localization integration', () => {
  it('renders localized operator context, hides UUIDs, and keeps raw text collapsed', () => {
    testState.locale = 'zh-CN';
    testState.alerts = [structuredAlert];

    render(<AlertsPage />);

    expect(screen.getByText('充电桩心跳超时')).toBeInTheDocument();
    expect(screen.getByText('充电桩已超过 90 秒未发送心跳。')).toBeInTheDocument();
    expect(screen.getByText('严重')).toBeInTheDocument();
    expect(screen.getByText('待处理')).toBeInTheDocument();
    expect(screen.getByText('SIM E2E Test Site')).toBeInTheDocument();
    expect(screen.getByText('SIM-E2E-CP-001')).toBeInTheDocument();
    expect(screen.getByText('EVSE 1')).toBeInTheDocument();

    expect(screen.getByRole('link', { name: '查看站点' })).toHaveAttribute('href', '/sites/site_0123456789abcdef');
    expect(screen.getByRole('link', { name: '查看设备' })).toHaveAttribute('href', '/chargers/SIM-E2E-CP-001');
    expect(screen.queryByText(structuredAlert.id)).not.toBeInTheDocument();
    expect(screen.queryByText(structuredAlert.charge_point_id)).not.toBeInTheDocument();
    expect(screen.queryByText(structuredAlert.evse_id)).not.toBeInTheDocument();

    const technicalDetails = screen.getByTestId('admin-alert-technical-details');
    expect(technicalDetails).not.toHaveAttribute('open');
    expect(within(technicalDetails).getByText(/OCPP WebSocket connection closed/)).toBeInTheDocument();
    expect(technicalDetails).toHaveTextContent('timeout_seconds');
    expect(technicalDetails).toHaveTextContent('heartbeat_timeout');
    expect(technicalDetails).not.toHaveTextContent('param-tenant-internal-uuid');
    expect(technicalDetails).not.toHaveTextContent('param-event-internal-uuid');
  });

  it.each([
    ['en', 'Charger heartbeat timeout', 'Critical', 'Pending'],
    ['es', 'Tiempo de espera del latido agotado', 'Crítica', 'Pendiente'],
  ] as const)('localizes title, description, severity, and status in %s', (locale, title, severity, status) => {
    testState.locale = locale;
    testState.alerts = [structuredAlert];

    render(<AlertsPage />);

    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByText(severity)).toBeInTheDocument();
    expect(screen.getByText(status)).toBeInTheDocument();
    expect(screen.queryByText(structuredAlert.title)).not.toBeInTheDocument();
    expect(screen.queryByText(structuredAlert.description)).not.toBeInTheDocument();
  });

  it('renders nullable relationships as unassigned and disables repeat handling for resolved alerts', () => {
    testState.locale = 'zh-CN';
    testState.alerts = [{
      ...structuredAlert,
      id: '55555555-5555-4555-8555-555555555555',
      charge_point_id: null,
      evse_id: null,
      alert_code: 'unknown.vendor.alert',
      message_params: {},
      raw_message: null,
      description: null,
      site: null,
      charge_point: null,
      evse: null,
      status: 'resolved',
    }];

    render(<AlertsPage />);

    expect(screen.getByText('系统告警')).toBeInTheDocument();
    expect(screen.getAllByText('未关联')).toHaveLength(3);
    expect(screen.queryByTestId('admin-alert-acknowledge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('admin-alert-resolve')).not.toBeInTheDocument();
  });

  it('keeps acknowledge and resolve actions for pending alerts', async () => {
    testState.locale = 'en';
    testState.alerts = [structuredAlert];
    testState.canWriteAlerts = true;
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    render(<AlertsPage />);
    fireEvent.click(screen.getByTestId('admin-alert-acknowledge'));
    fireEvent.click(screen.getByTestId('admin-alert-resolve'));

    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith(`/api/v1/admin/alerts/${structuredAlert.id}/acknowledge`);
      expect(apiPut).toHaveBeenCalledWith(`/api/v1/admin/alerts/${structuredAlert.id}/resolve`);
    });
  });

  it('hides acknowledge and resolve actions from read-only users', () => {
    testState.locale = 'en';
    testState.alerts = [structuredAlert];
    testState.canWriteAlerts = false;

    render(<AlertsPage />);

    expect(screen.getByText('Charger heartbeat timeout')).toBeInTheDocument();
    expect(screen.queryByTestId('admin-alert-acknowledge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('admin-alert-resolve')).not.toBeInTheDocument();
  });
});
