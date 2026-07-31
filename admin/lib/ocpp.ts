export function remoteCommandConfig(idempotencyKey: string) {
  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  };
}

export function remoteStartPayload(
  chargePointId: string,
  connectorId: number,
  operationReason: string
) {
  return {
    charge_point_id: chargePointId,
    connector_id: connectorId,
    operation_reason: operationReason,
  };
}

export function remoteStopPayload(
  sessionId: string,
  operationReason: string
) {
  return {
    session_id: sessionId,
    operation_reason: operationReason.trim(),
  };
}

export function resetPayload(
  chargePointId: string,
  type: 'Soft' | 'Hard',
  operationReason: string
) {
  return {
    charge_point_id: chargePointId,
    type,
    operation_reason: operationReason.trim(),
  };
}

export function unlockPayload(
  chargePointId: string,
  connectorId: number,
  operationReason: string
) {
  return {
    charge_point_id: chargePointId,
    connector_id: connectorId,
    operation_reason: operationReason.trim(),
  };
}
