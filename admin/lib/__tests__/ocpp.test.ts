import { describe, expect, it } from 'vitest';

import {
  remoteCommandConfig,
  remoteStartPayload,
  remoteStopPayload,
  resetPayload,
} from '@/lib/ocpp';

describe('OCPP admin payloads', () => {
  it('uses snake_case, requires an operation reason, and does not send a client id tag', () => {
    expect(remoteStartPayload('CO.BOGOTA:CP-01', 2, 'Remote assistance')).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      connector_id: 2,
      operation_reason: 'Remote assistance',
    });
    expect(resetPayload('CO.BOGOTA:CP-01', 'Hard', '  Recover unresponsive charger  ')).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      type: 'Hard',
      operation_reason: 'Recover unresponsive charger',
    });
  });

  it('stops with only the business session ID and operation reason', () => {
    expect(remoteStopPayload('internal-session-uuid', '  Driver requested support  ')).toEqual({
      session_id: 'internal-session-uuid',
      operation_reason: 'Driver requested support',
    });
  });

  it('passes one stable idempotency key in the remote apiPost request config', () => {
    const actionKey = 'adm-action-123';
    const config = remoteCommandConfig(actionKey);

    expect(config).toEqual({ headers: { 'Idempotency-Key': actionKey } });
    expect(config.headers['Idempotency-Key']).toBe(actionKey);
  });
});
