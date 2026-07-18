import { describe, expect, it } from 'vitest';

import {
  activeTransactionFor,
  remoteCommandConfig,
  remoteStartPayload,
  remoteStopPayload,
  resetPayload,
} from '@/lib/ocpp';
import type { Transaction } from '@/types';

const sessions: Transaction[] = [
  {
    id: 'internal-session-uuid',
    transaction_id: 731,
    charge_point_id: 'a17f30f0-dbb8-4c86-bc6a-e4bb3d1b0e3d',
    ocpp_identity: 'CO.BOGOTA:CP-01',
    id_tag: 'driver',
    start_time: '2026-07-17T12:00:00Z',
    status: 'ongoing',
  },
];

describe('OCPP admin payloads', () => {
  it('uses snake_case for remote start and reset', () => {
    expect(remoteStartPayload('CO.BOGOTA:CP-01', 2)).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      id_tag: 'admin',
      connector_id: 2,
    });
    expect(resetPayload('CO.BOGOTA:CP-01', 'Hard')).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      type: 'Hard',
    });
  });

  it('stops with the active OCPP transaction ID, not the EVSE ID', () => {
    const active = activeTransactionFor(sessions, 'a17f30f0-dbb8-4c86-bc6a-e4bb3d1b0e3d');
    expect(active?.transaction_id).toBe(731);
    expect(remoteStopPayload('CO.BOGOTA:CP-01', active!.transaction_id)).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      transaction_id: 731,
    });
  });

  it('does not select completed or cross-charger sessions', () => {
    expect(
      activeTransactionFor(
        [{ ...sessions[0], status: 'completed' }],
        'a17f30f0-dbb8-4c86-bc6a-e4bb3d1b0e3d'
      )
    ).toBeUndefined();
    expect(activeTransactionFor(sessions, 'different-charger-uuid')).toBeUndefined();
  });

  it('matches by internal UUID when UUID and OCPP identity differ', () => {
    expect(activeTransactionFor(sessions, sessions[0].charge_point_id)).toBe(sessions[0]);
    expect(activeTransactionFor(sessions, sessions[0].ocpp_identity)).toBeUndefined();
    expect(remoteStopPayload(sessions[0].ocpp_identity!, sessions[0].transaction_id)).toEqual({
      charge_point_id: 'CO.BOGOTA:CP-01',
      transaction_id: 731,
    });
  });

  it('passes one stable idempotency key in the remote apiPost request config', () => {
    const actionKey = 'adm-action-123';
    const config = remoteCommandConfig(actionKey);

    expect(config).toEqual({ headers: { 'Idempotency-Key': actionKey } });
    expect(config.headers['Idempotency-Key']).toBe(actionKey);
  });
});
