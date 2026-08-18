/** PAY-MP-002 Admin-only contract types. No App store or auth state is shared. */

export const PAY_MP_002_MEDIA_TYPE = 'application/vnd.eslatin.pay-mp-002.v1+json' as const;
export type DecimalString = string;
export type UtcTimestamp = string;
export type OpaqueId = string;

export type CanonicalResourceStatus =
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'provider_processing'
  | 'partially_refunded'
  | 'refunded'
  | 'rejected'
  | 'manual_review'
  | 'received'
  | 'hold'
  | 'representment'
  | 'won'
  | 'lost'
  | 'reversed'
  | 'created'
  | 'running'
  | 'completed'
  | 'completed_with_exceptions'
  | 'failed'
  | 'matched'
  | 'pending'
  | 'mismatch'
  | 'temporarily_accepted'
  | 'closed'
  | 'not_required'
  | 'expired'
  | 'open'
  | 'acknowledged'
  | 'in_progress'
  | 'waiting_user'
  | 'resolved'
  | 'unknown';

export type ApprovalStatus = 'not_required' | 'pending' | 'approved' | 'rejected' | 'expired' | 'unknown';

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
  page: { next_cursor: string | null; has_more: boolean };
}

export interface ActorRef {
  id: OpaqueId;
  display_name: string;
  role_label: string;
}

export interface ApprovalProjection {
  status: ApprovalStatus;
  initiator: ActorRef | null;
  approver: ActorRef | null;
  requested_at: UtcTimestamp | null;
  decided_at: UtcTimestamp | null;
  expires_at: UtcTimestamp | null;
  version: number;
}

export interface RefundCaseProjection {
  case_id: OpaqueId;
  target: { resource_type: string; resource_id: OpaqueId };
  requested_amount: DecimalString;
  approved_amount: DecimalString | null;
  confirmed_refunded_amount: DecimalString;
  currency: string;
  status: Extract<CanonicalResourceStatus, 'submitted' | 'under_review' | 'approved' | 'provider_processing' | 'partially_refunded' | 'refunded' | 'rejected' | 'manual_review' | 'unknown'>;
  approval: ApprovalProjection;
  provider_reference: string | null;
  timeline: unknown[];
  audit_references: string[];
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface RuntimeRailControlProjection {
  control_id: OpaqueId;
  axis: 'paid_admission' | 'payment_creation';
  scope: { type: 'platform' | 'provider' | 'tenant' | 'site'; ref: string };
  status: 'open' | 'closed' | 'unknown';
  reason: string | null;
  incident_reference: string | null;
  effective_at: UtcTimestamp | null;
  closed_by: ActorRef | null;
  reopened_by: ActorRef | null;
  health_check_reference: string | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export type RailReopenRequestStatus = 'requested' | 'approved' | 'rejected' | 'expired' | 'unknown';

export interface RailReopenRequestProjection {
  request_id: OpaqueId;
  control_id: OpaqueId;
  status: RailReopenRequestStatus;
  reason: string;
  initiator: ActorRef | null;
  approver: ActorRef | null;
  health_check_reference: string;
  control_status: RuntimeRailControlProjection['status'];
  expires_at: UtcTimestamp;
  decided_at: UtcTimestamp | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface SupportCaseProjection {
  case_id: OpaqueId;
  reference: string;
  status: 'open' | 'acknowledged' | 'in_progress' | 'waiting_user' | 'resolved' | 'closed' | 'unknown';
  category: string;
  linked_resources: unknown[];
  sla_target_at: UtcTimestamp | null;
  assignee: ActorRef | null;
  timeline: unknown[];
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface ChargebackCaseProjection {
  case_id: OpaqueId;
  payment_reference: string;
  invoice_reference: string;
  amount: DecimalString;
  currency: string;
  status: Extract<CanonicalResourceStatus, 'received' | 'under_review' | 'hold' | 'representment' | 'won' | 'lost' | 'reversed' | 'unknown'>;
  deadline_at: UtcTimestamp | null;
  funds_state: string;
  timeline: unknown[];
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface ReconciliationRunProjection {
  run_id: OpaqueId;
  business_date: string;
  run_type: string;
  status: Extract<CanonicalResourceStatus, 'created' | 'running' | 'completed' | 'completed_with_exceptions' | 'failed' | 'unknown'>;
  cutoff_at: UtcTimestamp | null;
  closed_at: UtcTimestamp | null;
  source_watermarks: Record<string, unknown>;
  summary: Record<string, unknown>;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface ReconciliationItemProjection {
  item_id: OpaqueId;
  run_id: OpaqueId;
  eslatin_reference: string | null;
  provider_reference: string | null;
  funds_reference: string | null;
  amount: DecimalString | null;
  currency: string;
  match_status: string;
  reason_codes: string[];
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface ReconciliationExceptionProjection {
  exception_id: OpaqueId;
  item_id: OpaqueId;
  status: Extract<CanonicalResourceStatus, 'matched' | 'pending' | 'mismatch' | 'manual_review' | 'temporarily_accepted' | 'closed' | 'unknown'>;
  category: string;
  difference_amount: DecimalString | null;
  currency: string;
  severity: string;
  owner: string | null;
  due_at: UtcTimestamp | null;
  temporary_acceptance_until: UtcTimestamp | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface ResolutionIntentProjection {
  intent_id: OpaqueId;
  exception_id: OpaqueId;
  resolution_code: string;
  reason: string;
  status: CanonicalResourceStatus;
  initiator: ActorRef | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface TemporaryAcceptanceRequestProjection {
  request_id: OpaqueId;
  exception_id: OpaqueId;
  status: CanonicalResourceStatus;
  reason: string;
  initiator: ActorRef | null;
  approver: ActorRef | null;
  expires_at: UtcTimestamp;
  decided_at: UtcTimestamp | null;
  allowed_actions: string[];
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export type ReconciliationExportStatus = 'queued' | 'generating' | 'ready' | 'downloaded' | 'failed' | 'expired';

export interface ReconciliationExportProjection {
  export_id: OpaqueId;
  status: ReconciliationExportStatus;
  download_path: string | null;
  expires_at: UtcTimestamp;
  audit_reference: string;
  version: number;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
}

export interface AuditEventProjection {
  event_id: OpaqueId;
  actor: ActorRef | null;
  resource: { type: string; id: OpaqueId };
  action: string;
  result: string;
  scope: { type: 'platform' | 'tenant' | 'provider' | 'site'; ref: string };
  reason_code: string | null;
  safe_metadata: Record<string, unknown>;
  occurred_at: UtcTimestamp;
}
