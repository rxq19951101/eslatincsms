import type {
  FinancialEligibilityStatus,
  PaymentAllocationStatus,
  RecoveryAttemptProjection,
  RecoveryAttemptStatus,
} from './types';

export type PayMp002ViewState =
  | 'loading'
  | 'empty'
  | 'ready'
  | 'processing'
  | 'action_required'
  | 'unknown'
  | 'error'
  | 'recovery';

export interface AsyncViewState<T> {
  status: PayMp002ViewState;
  data: T | null;
  error: { code: string; reference: string | null } | null;
}

const publicRecoveryStates: ReadonlySet<RecoveryAttemptStatus> = new Set([
  'created',
  'processing',
  'action_required',
  'approved',
  'allocated',
  'declined',
  'failed',
  'cancelled',
  'expired',
  'manual_review',
  'unknown',
]);

export function recoveryViewState(status: RecoveryAttemptStatus): PayMp002ViewState {
  if (!publicRecoveryStates.has(status)) return 'unknown';
  if (status === 'action_required') return 'action_required';
  if (status === 'unknown' || status === 'manual_review') return 'unknown';
  if (status === 'allocated') return 'ready';
  if (status === 'declined' || status === 'failed' || status === 'expired' || status === 'cancelled') {
    return 'error';
  }
  return 'processing';
}

export function recoveryProjectionViewState(
  attempt: RecoveryAttemptProjection,
): PayMp002ViewState {
  const state = recoveryViewState(attempt.status);
  if (state !== 'ready') return state;
  return attempt.allocation?.status === 'confirmed'
    && attempt.financial_eligibility.status === 'eligible'
    ? 'ready'
    : 'recovery';
}

export function normalizeRecoveryStatus(value: unknown): RecoveryAttemptStatus {
  switch (value) {
    case 'created':
    case 'processing':
    case 'action_required':
    case 'approved':
    case 'allocated':
    case 'declined':
    case 'failed':
    case 'cancelled':
    case 'expired':
    case 'manual_review':
    case 'unknown':
      return value;
    case 'provider_approved':
      return 'approved';
    case 'duplicate_approved':
      return 'manual_review';
    default:
      return 'unknown';
  }
}

export function normalizeAllocationStatus(value: unknown): PaymentAllocationStatus {
  switch (value) {
    case 'pending':
    case 'confirmed':
    case 'reversed':
    case 'failed':
    case 'unknown':
      return value;
    case 'committed':
      return 'confirmed';
    case 'needs_review':
      return 'unknown';
    default:
      return 'unknown';
  }
}

export function normalizeEligibilityStatus(value: unknown): FinancialEligibilityStatus {
  switch (value) {
    case 'eligible':
    case 'blocked':
    case 'evaluating':
    case 'unknown':
      return value;
    case 'recheck_required':
      return 'evaluating';
    default:
      return 'unknown';
  }
}
