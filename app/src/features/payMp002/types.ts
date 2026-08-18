/**
 * PAY-MP-002 App-only contract types.
 *
 * This module deliberately does not share a runtime store with Admin. Decimal
 * values remain strings so presentation cannot accidentally become authority.
 */

export const PAY_MP_002_MEDIA_TYPE = 'application/vnd.eslatin.pay-mp-002.v1+json' as const;

export type DecimalString = string;
export type OpaqueId = string;
export type UtcTimestamp = string;

export type RecoveryAttemptStatus =
  | 'created'
  | 'processing'
  | 'action_required'
  | 'approved'
  | 'allocated'
  | 'declined'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'manual_review'
  | 'unknown';

export type PaymentAllocationStatus =
  | 'pending'
  | 'confirmed'
  | 'reversed'
  | 'failed'
  | 'unknown';

export type FinancialEligibilityStatus = 'eligible' | 'blocked' | 'evaluating' | 'unknown';

export type RecoveryMethod = 'wallet' | 'new_card' | 'saved_card';

export interface CanonicalError {
  code: string;
  message: string;
  reference: string | null;
  retryable: boolean;
  retry_after_seconds: number | null;
  current_version?: number;
}

export interface CursorPage<T> {
  items: T[];
  page: {
    next_cursor: string | null;
    has_more: boolean;
  };
}

export interface PaymentAllocationProjection {
  status: PaymentAllocationStatus;
  amount: DecimalString;
  confirmed_at: UtcTimestamp | null;
}

export interface FinancialEligibilityProjection {
  status: FinancialEligibilityStatus;
  reason_codes: string[];
  evaluated_at: UtcTimestamp;
  version: number;
}

export interface RecoveryNextAction {
  type: 'none' | 'poll' | 'open_checkout' | 'open_provider_url' | 'contact_support';
  checkout_session_id?: OpaqueId | null;
  url?: string | null;
  expires_at?: UtcTimestamp | null;
  poll_after_seconds?: number | null;
}

export interface RecoveryAttemptProjection {
  attempt_id: OpaqueId;
  invoice_id: OpaqueId;
  target_amount: DecimalString;
  currency: string;
  method: RecoveryMethod;
  status: RecoveryAttemptStatus;
  reason_code?: string | null;
  payment_order_id?: OpaqueId | null;
  allocation: PaymentAllocationProjection | null;
  financial_eligibility: FinancialEligibilityProjection;
  next_action: RecoveryNextAction;
  support_reference: string | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface SavedPaymentMethodRef {
  id: OpaqueId;
  brand: string;
  last_four: string;
  is_default: boolean;
}

export interface RecoveryMethodOption {
  method: RecoveryMethod;
  enabled: boolean;
  disabled_reason_code: string | null;
  saved_payment_method_ref?: SavedPaymentMethodRef;
}

export interface UnpaidInvoiceProjection {
  invoice_id: OpaqueId;
  invoice_reference: string;
  session_id: OpaqueId;
  site: string | null;
  charge_point_reference: string | null;
  connector_id: number | null;
  started_at: UtcTimestamp | null;
  ended_at: UtcTimestamp | null;
  energy_kwh: DecimalString;
  original_amount: DecimalString;
  allocated_amount: DecimalString;
  refunded_amount: DecimalString;
  outstanding_amount: DecimalString;
  currency: string;
  blocking_reason: string;
  recovery_status: string | null;
  active_recovery_attempt_id: OpaqueId | null;
  d1_status: 'blocked';
  allowed_actions: string[];
  updated_at: UtcTimestamp;
}

export interface RecoveryTimelineItem {
  type: string;
  status: string;
  occurred_at: UtcTimestamp | null;
  reference: string | null;
}

export interface UnpaidInvoiceDetail extends UnpaidInvoiceProjection {
  available_methods: RecoveryMethodOption[];
  active_recovery_attempt: RecoveryAttemptProjection | null;
  timeline: RecoveryTimelineItem[];
  financial_eligibility: FinancialEligibilityProjection;
  support_case_refs: string[];
}

export interface P001TransactionProjection {
  id: string;
  transaction_id: number;
  charge_point_id: string;
  ocpp_identity: string | null;
  evse_id: string;
  start_time: UtcTimestamp | null;
  end_time: UtcTimestamp | null;
  status: string;
  energy_kwh: number | null;
  duration_minutes: number | null;
  site_name: string | null;
  site_address: string | null;
}

export type P002PaymentStatus =
  | 'paid'
  | 'processing'
  | 'unpaid'
  | 'refunded'
  | 'partially_refunded'
  | 'disputed'
  | 'unknown';

export type P002DataQuality = 'current' | 'legacy' | 'unknown';

export type P002InvoiceStatus =
  | 'pending'
  | 'paid'
  | 'cancelled'
  | 'refunded'
  | 'unknown';

export interface P002InvoiceProjection {
  id: OpaqueId;
  reference: string;
  status: P002InvoiceStatus;
  amount: DecimalString | null;
  currency: string;
  issued_at: UtcTimestamp | null;
  paid_at: UtcTimestamp | null;
  pricing_snapshot_reference: OpaqueId | null;
}

export type P002PaymentFactStatus = 'paid' | 'processing' | 'unpaid' | 'refunded' | 'unknown';

export interface P002PaymentFact {
  id: OpaqueId;
  reference: string;
  status: P002PaymentFactStatus;
  method: string | null;
  amount: DecimalString | null;
  currency: string;
  occurred_at: UtcTimestamp | null;
  updated_at: UtcTimestamp | null;
}

export interface P002TimelineItem {
  event_id: OpaqueId;
  type: string;
  status: string;
  occurred_at: UtcTimestamp;
  actor: string | null;
  reason_code: string | null;
  reference: string;
}

export interface P002TransactionProjection {
  id: string;
  transaction_id: number;
  charge_point_id: string;
  ocpp_identity: string | null;
  evse_id: string;
  start_time: UtcTimestamp | null;
  end_time: UtcTimestamp | null;
  status: string;
  energy_kwh: DecimalString | null;
  duration_minutes: DecimalString | null;
  site_name: string | null;
  site_address: string | null;
  session?: {
    id: OpaqueId;
    reference: string;
    status: string;
    started_at: UtcTimestamp | null;
    ended_at: UtcTimestamp | null;
  };
  invoice?: P002InvoiceProjection | null;
  payments?: P002PaymentFact[];
  recovery_attempts?: Array<{
    id: OpaqueId;
    reference: string;
    status: string;
    method: string | null;
    target_amount: DecimalString | null;
    allocated_amount: DecimalString | null;
    currency: string;
    updated_at: UtcTimestamp | null;
  }>;
  allocations?: Array<{
    id: OpaqueId;
    reference: string;
    status: string;
    method: string | null;
    amount: DecimalString | null;
    currency: string;
    confirmed_at: UtcTimestamp | null;
    updated_at: UtcTimestamp | null;
  }>;
  refunds?: Array<{
    id: OpaqueId;
    reference: string;
    status: string;
    requested_amount: DecimalString | null;
    approved_amount: DecimalString | null;
    confirmed_refunded_amount: DecimalString | null;
    currency: string;
    updated_at: UtcTimestamp | null;
  }>;
  chargebacks?: Array<{
    id: OpaqueId;
    reference: string;
    status: string;
    amount: DecimalString | null;
    currency: string;
    received_at: UtcTimestamp | null;
    updated_at: UtcTimestamp | null;
  }>;
  payment_status?: P002PaymentStatus;
  data_quality?: P002DataQuality;
  support_case_refs?: string[];
  allowed_actions?: string[];
  updated_at?: UtcTimestamp;
  meter_start?: number | null;
  meter_stop?: number | null;
  invoice_number?: string | null;
  total_amount?: DecimalString | null;
  currency?: string;
  billing_status?: P002InvoiceStatus | null;
  pricing_snapshot?: Record<string, unknown> | null;
  connector_number?: number | null;
  connector_label?: string | null;
  charge_point_label?: string | null;
  timeline?: P002TimelineItem[];
}

export type SupportCaseStatus =
  | 'open'
  | 'acknowledged'
  | 'in_progress'
  | 'waiting_user'
  | 'resolved'
  | 'closed'
  | 'unknown';

export interface SupportCaseResourceRef {
  type: string;
  id: OpaqueId;
  reference: string | null;
}

export interface SupportCaseTimelineItem {
  event_id: OpaqueId;
  case_id: OpaqueId;
  event_type: string;
  note_visibility: 'user' | 'internal' | string;
  status: SupportCaseStatus;
  actor: { id: OpaqueId; display_name: string; role_label: string };
  occurred_at: UtcTimestamp;
  case_version: number;
}

export interface SupportCaseProjection {
  case_id: OpaqueId;
  reference: string;
  status: SupportCaseStatus;
  category: string;
  linked_resources: SupportCaseResourceRef[];
  sla_target_at: UtcTimestamp | null;
  assignee: { id: OpaqueId; display_name: string; role_label: string } | null;
  timeline: SupportCaseTimelineItem[];
  linked_refund_case?: SupportCaseResourceRef | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface AdminActorRef {
  id: OpaqueId;
  display_name: string;
  role_label: string;
}

export interface ApprovalProjection {
  status: 'not_required' | 'pending' | 'approved' | 'rejected' | 'expired' | 'unknown';
  initiator: AdminActorRef | null;
  approver: AdminActorRef | null;
  requested_at: UtcTimestamp | null;
  decided_at: UtcTimestamp | null;
  expires_at: UtcTimestamp | null;
  version: number;
}
