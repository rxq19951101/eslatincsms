import type { Transaction } from '@/types';

export function remoteCommandConfig(idempotencyKey: string) {
  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  };
}

export function remoteStartPayload(chargePointId: string, connectorId: number, idTag = 'admin') {
  return {
    charge_point_id: chargePointId,
    id_tag: idTag,
    connector_id: connectorId,
  };
}

export function activeTransactionFor(
  sessions: Transaction[] | undefined,
  internalChargePointId: string | undefined
): Transaction | undefined {
  if (!internalChargePointId) return undefined;
  return sessions?.find(
    (session) =>
      session.charge_point_id === internalChargePointId &&
      session.status.toLowerCase() === 'ongoing'
  );
}

export function remoteStopPayload(chargePointId: string, transactionId: string | number) {
  return {
    charge_point_id: chargePointId,
    transaction_id: transactionId,
  };
}

export function resetPayload(chargePointId: string, type: 'Soft' | 'Hard') {
  return {
    charge_point_id: chargePointId,
    type,
  };
}
