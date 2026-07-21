import { describe, expect, it } from 'vitest';
import type { Alert } from '@/types';
import {
  alertSeverityLabel,
  alertStatusLabel,
  localizedAlertMessage,
  sanitizedAlertMessageParams,
} from '../alert-i18n';

const baseAlert = {
  id: 'alert-internal-id',
  tenant_id: 'tenant-internal-id',
  alert_type: 'system',
  severity: 'warning',
  status: 'acknowledged',
  title: 'Raw title',
  description: 'Raw description',
  metadata: {},
  created_at: '2026-07-21T00:00:00Z',
  updated_at: '2026-07-21T00:00:00Z',
} satisfies Alert;

describe('alert-specific i18n', () => {
  it.each([
    ['zh-CN', '充电桩已超过 90 秒未发送心跳。', '警告', '已确认'],
    ['en', 'The charger has not sent a heartbeat for more than 90 seconds.', 'Warning', 'Acknowledged'],
    ['es', 'El cargador no ha enviado un latido durante más de 90 segundos.', 'Advertencia', 'Confirmada'],
  ] as const)('interpolates alert_code params and labels in %s', (locale, description, severity, status) => {
    const alert: Alert = {
      ...baseAlert,
      alert_code: 'charger.offline.heartbeat_timeout',
      message_params: { timeout_seconds: 90 },
    };

    expect(localizedAlertMessage(locale, alert).description).toBe(description);
    expect(alertSeverityLabel(locale, alert.severity)).toBe(severity);
    expect(alertStatusLabel(locale, alert.status)).toBe(status);
  });

  it.each([
    'charger.offline.heartbeat_timeout',
    'charger.offline.websocket_disconnected',
    'charger.faulted',
    'device.event',
    'manual',
  ])('provides localized content for P0 code %s', (alertCode) => {
    for (const locale of ['zh-CN', 'en', 'es'] as const) {
      const message = localizedAlertMessage(locale, { ...baseAlert, alert_code: alertCode });
      expect(message.title).not.toBe('Raw title');
      expect(message.description).not.toBe('Raw description');
    }
  });

  it('uses localized generic content for unknown codes', () => {
    const alert: Alert = { ...baseAlert, alert_code: 'vendor.future.code' };

    expect(localizedAlertMessage('zh-CN', alert).title).toBe('系统告警');
    expect(localizedAlertMessage('en', alert).title).toBe('System alert');
    expect(localizedAlertMessage('es', alert).title).toBe('Alerta del sistema');
  });

  it('recursively removes internal IDs from technical message params', () => {
    expect(sanitizedAlertMessageParams({
      id: 'alert-uuid',
      tenant_id: 'tenant-uuid',
      charge_point_id: 'charge-point-uuid',
      evse_id: 'evse-uuid',
      event_id: 'event-uuid',
      rule_id: 'rule-uuid',
      timeout_seconds: 90,
      nested: {
        id: 'nested-uuid',
        connector_id: 'connector-uuid',
        reason: 'heartbeat_timeout',
      },
      events: [{ event_id: 'array-event-uuid', value: 'kept' }],
    })).toEqual({
      timeout_seconds: 90,
      nested: { reason: 'heartbeat_timeout' },
      events: [{ value: 'kept' }],
    });
  });
});
