import type { ApprovalStatus, CanonicalResourceStatus } from './payMp002Types';

export type PayMp002ViewState =
  | 'loading'
  | 'empty'
  | 'ready'
  | 'processing'
  | 'action_required'
  | 'unknown'
  | 'error'
  | 'recovery';

const knownStatuses: ReadonlySet<CanonicalResourceStatus> = new Set([
  'submitted', 'under_review', 'approved', 'provider_processing', 'partially_refunded',
  'refunded', 'rejected', 'manual_review', 'received', 'hold', 'representment', 'won',
  'lost', 'reversed', 'created', 'running', 'completed', 'completed_with_exceptions',
  'failed', 'matched', 'pending', 'mismatch', 'temporarily_accepted', 'closed',
  'not_required', 'expired', 'open', 'acknowledged', 'in_progress', 'waiting_user',
  'resolved', 'unknown',
]);

export function normalizeAdminStatus(value: unknown): CanonicalResourceStatus {
  return typeof value === 'string' && knownStatuses.has(value as CanonicalResourceStatus)
    ? value as CanonicalResourceStatus
    : 'unknown';
}

export function normalizeApprovalStatus(value: unknown): ApprovalStatus {
  switch (value) {
    case 'not_required':
    case 'pending':
    case 'approved':
    case 'rejected':
    case 'expired':
    case 'unknown':
      return value;
    default:
      return 'unknown';
  }
}

export function adminResourceViewState(status: CanonicalResourceStatus): PayMp002ViewState {
  if (status === 'unknown') return 'unknown';
  if (status === 'provider_processing' || status === 'pending' || status === 'running' || status === 'created') {
    return 'processing';
  }
  if (status === 'under_review' || status === 'manual_review' || status === 'hold') return 'recovery';
  if (status === 'failed' || status === 'rejected' || status === 'expired') return 'error';
  return 'ready';
}
