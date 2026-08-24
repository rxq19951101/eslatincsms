import { apiGet, apiPost, ApiRequestError } from './api';
import { normalizeAdminStatus, normalizeApprovalStatus } from './payMp002Status';
import {
  PAY_MP_002_MEDIA_TYPE,
  type CanonicalError,
  type ChargebackCaseProjection,
  type CursorPage,
  type AuditEventProjection,
  type ReconciliationExceptionProjection,
  type ReconciliationExportProjection,
  type ReconciliationItemProjection,
  type ReconciliationRunProjection,
  type ResolutionIntentProjection,
  type RefundCaseProjection,
  type RailReopenRequestProjection,
  type RuntimeRailControlProjection,
  type RailReopenRequestStatus,
  type SupportCaseProjection,
  type TemporaryAcceptanceRequestProjection,
} from './payMp002Types';

const DECIMAL_STRING = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;
const P002_BASE = '/api/v1';

export class PayMp002AdminError extends Error {
  constructor(
    public readonly canonical: CanonicalError,
    public readonly httpStatus?: number,
  ) {
    super(canonical.message);
    this.name = 'PayMp002AdminError';
  }
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function safeReference(value: unknown): string | null {
  return typeof value === 'string' && value.length <= 256 ? value : null;
}

function safeTimestamp(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function safeVersion(value: unknown): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : 0;
}

function safeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => safeReference(item) !== null)
    : [];
}

function decodeActor(value: unknown) {
  if (value === null || value === undefined) return null;
  const actor = record(value);
  const id = safeReference(actor.id);
  const displayName = safeReference(actor.display_name);
  const roleLabel = safeReference(actor.role_label);
  if (id === null || displayName === null || roleLabel === null) return null;
  return { id, display_name: displayName, role_label: roleLabel };
}

function decodeSafeTimeline(value: unknown): unknown[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const event = record(item);
    return {
      event_id: safeReference(event.event_id),
      type: safeReference(event.type),
      status: safeReference(event.status),
      occurred_at: safeTimestamp(event.occurred_at),
      actor: decodeActor(event.actor),
      reason_code: event.reason_code === null ? null : safeReference(event.reason_code),
      reference: event.reference === null ? null : safeReference(event.reference),
    };
  });
}

function decodeLinkedResources(value: unknown): unknown[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const resource = record(item);
    return {
      type: safeReference(resource.type),
      id: safeReference(resource.id),
      reference: resource.reference === null ? null : safeReference(resource.reference),
    };
  });
}

const SENSITIVE_KEY_PARTS = [
  'pan',
  'pannumber',
  'cvv',
  'token',
  'secret',
  'credential',
  'rawproviderpayload',
  'providerpayload',
] as const;

function isSensitiveKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, '').toLowerCase();
  return SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part));
}

function sanitizeSafeValue(value: unknown, depth = 0): unknown {
  if (depth > 8) return undefined;
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((entry) => sanitizeSafeValue(entry, depth + 1))
      .filter((entry): entry is Exclude<typeof entry, undefined> => entry !== undefined);
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).reduce<Record<string, unknown>>((result, [key, entry]) => {
      if (isSensitiveKey(key)) return result;
      const sanitized = sanitizeSafeValue(entry, depth + 1);
      if (sanitized !== undefined) result[key] = sanitized;
      return result;
    }, {});
  }
  return undefined;
}

function safeObject(value: unknown): Record<string, unknown> {
  const sanitized = sanitizeSafeValue(value);
  return sanitized && typeof sanitized === 'object' && !Array.isArray(sanitized)
    ? sanitized as Record<string, unknown>
    : {};
}

function decodeScope(value: unknown) {
  const scope = record(value);
  return {
    type: safeReference(scope.type) as 'platform' | 'tenant' | 'provider' | 'site',
    ref: safeReference(scope.ref) ?? '',
  };
}

function decodeApproval(value: unknown) {
  const approval = record(value);
  return {
    status: normalizeApprovalStatus(approval.status),
    initiator: decodeActor(approval.initiator),
    approver: decodeActor(approval.approver),
    requested_at: safeTimestamp(approval.requested_at),
    decided_at: safeTimestamp(approval.decided_at),
    expires_at: safeTimestamp(approval.expires_at),
    version: safeVersion(approval.version),
  };
}

function toCanonicalError(error: unknown): PayMp002AdminError {
  if (error instanceof PayMp002AdminError) return error;
  if (error instanceof ApiRequestError) {
    const candidate = error as ApiRequestError & {
      code?: string;
      reference?: string | null;
      retryable?: boolean;
      retryAfterSeconds?: number | null;
      canonical?: {
        code?: string;
        reference?: string | null;
        retryable?: boolean;
        retryAfterSeconds?: number | null;
        currentVersion?: number;
      };
      currentVersion?: number;
    };
    const canonical = candidate.canonical;
    return new PayMp002AdminError({
      code: candidate.code ?? canonical?.code ?? `HTTP_${candidate.status}`,
      message: candidate.message,
      reference: safeReference(candidate.reference ?? canonical?.reference),
      retryable: candidate.retryable ?? canonical?.retryable ?? candidate.status >= 500,
      retry_after_seconds: candidate.retryAfterSeconds ?? canonical?.retryAfterSeconds ?? (
        candidate.retryAfterMs ? Math.ceil(candidate.retryAfterMs / 1000) : null
      ),
      current_version: candidate.currentVersion ?? canonical?.currentVersion,
    }, candidate.status);
  }
  return new PayMp002AdminError({
    code: 'NETWORK_ERROR',
    message: 'The request could not be completed',
    reference: null,
    retryable: true,
    retry_after_seconds: null,
  });
}

function decodeCursorPage<T>(payload: unknown, decodeItem: (item: unknown) => T): CursorPage<T> {
  const value = record(payload);
  const page = record(value.page);
  if (!Array.isArray(value.items) ||
      !(typeof page.next_cursor === 'string' || page.next_cursor === null) ||
      typeof page.has_more !== 'boolean') {
    throw new PayMp002AdminError({
      code: 'RESPONSE_INVALID',
      message: 'Invalid cursor page projection',
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    });
  }
  return {
    items: value.items.map(decodeItem),
    page: { next_cursor: page.next_cursor, has_more: page.has_more },
  };
}

function assertDecimal(value: unknown, field: string): asserts value is string {
  if (typeof value !== 'string' || !DECIMAL_STRING.test(value)) {
    throw new PayMp002AdminError({
      code: 'RESPONSE_INVALID',
      message: `Invalid ${field} projection`,
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    });
  }
}

function safeDecimalOrNull(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null;
  assertDecimal(value, field);
  return value;
}

function decodeRefundCase(item: unknown): RefundCaseProjection {
  const value = record(item);
  assertDecimal(value.requested_amount, 'requested_amount');
  assertDecimal(value.confirmed_refunded_amount, 'confirmed_refunded_amount');
  if (value.approved_amount !== null) assertDecimal(value.approved_amount, 'approved_amount');
  const target = record(value.target);
  return {
    case_id: safeReference(value.case_id) ?? '',
    target: {
      resource_type: safeReference(target.resource_type) ?? '',
      resource_id: safeReference(target.resource_id) ?? '',
    },
    requested_amount: value.requested_amount as string,
    approved_amount: value.approved_amount as string | null,
    confirmed_refunded_amount: value.confirmed_refunded_amount as string,
    currency: safeReference(value.currency) ?? '',
    status: normalizeAdminStatus(value.status) as RefundCaseProjection['status'],
    approval: decodeApproval(value.approval),
    provider_reference: value.provider_reference === null ? null : safeReference(value.provider_reference),
    timeline: decodeSafeTimeline(value.timeline),
    audit_references: safeStringArray(value.audit_references),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  } as RefundCaseProjection;
}

function decodeRail(item: unknown): RuntimeRailControlProjection {
  const value = record(item);
  const scope = record(value.scope);
  return {
    control_id: safeReference(value.control_id) ?? '',
    axis: safeReference(value.axis) as RuntimeRailControlProjection['axis'],
    scope: {
      type: safeReference(scope.type) as RuntimeRailControlProjection['scope']['type'],
      ref: safeReference(scope.ref) ?? '',
    },
    status: normalizeAdminStatus(value.status) as RuntimeRailControlProjection['status'],
    reason: value.reason === null ? null : safeReference(value.reason),
    incident_reference: value.incident_reference === null ? null : safeReference(value.incident_reference),
    effective_at: safeTimestamp(value.effective_at),
    closed_by: decodeActor(value.closed_by),
    reopened_by: decodeActor(value.reopened_by),
    health_check_reference: value.health_check_reference === null ? null : safeReference(value.health_check_reference),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  } as RuntimeRailControlProjection;
}

function normalizeRailReopenStatus(value: unknown): RailReopenRequestStatus {
  switch (value) {
    case 'requested':
    case 'approved':
    case 'rejected':
    case 'expired':
      return value;
    default:
      return 'unknown';
  }
}

function decodeRailReopenRequest(item: unknown): RailReopenRequestProjection {
  const value = record(item);
  return {
    request_id: safeReference(value.request_id) ?? '',
    control_id: safeReference(value.control_id) ?? '',
    status: normalizeRailReopenStatus(value.status),
    reason: safeReference(value.reason) ?? '',
    initiator: decodeActor(value.initiator),
    approver: decodeActor(value.approver),
    health_check_reference: safeReference(value.health_check_reference) ?? '',
    control_status: normalizeAdminStatus(value.control_status) as RuntimeRailControlProjection['status'],
    expires_at: safeTimestamp(value.expires_at) as string,
    decided_at: safeTimestamp(value.decided_at),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeSupportCase(item: unknown): SupportCaseProjection {
  const value = record(item);
  return {
    case_id: safeReference(value.case_id) ?? '',
    reference: safeReference(value.reference) ?? '',
    status: normalizeAdminStatus(value.status) as SupportCaseProjection['status'],
    category: safeReference(value.category) ?? '',
    linked_resources: decodeLinkedResources(value.linked_resources),
    sla_target_at: safeTimestamp(value.sla_target_at),
    assignee: decodeActor(value.assignee),
    timeline: decodeSafeTimeline(value.timeline),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  } as SupportCaseProjection;
}

function decodeChargebackCase(item: unknown): ChargebackCaseProjection {
  const value = record(item);
  assertDecimal(value.amount, 'amount');
  return {
    case_id: safeReference(value.case_id) ?? '',
    payment_reference: safeReference(value.payment_reference) ?? '',
    invoice_reference: safeReference(value.invoice_reference) ?? '',
    amount: value.amount as string,
    currency: safeReference(value.currency) ?? '',
    status: normalizeAdminStatus(value.status) as ChargebackCaseProjection['status'],
    deadline_at: safeTimestamp(value.deadline_at),
    funds_state: safeReference(value.funds_state) ?? 'unknown',
    timeline: decodeSafeTimeline(value.timeline),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeReconciliationRun(item: unknown): ReconciliationRunProjection {
  const value = record(item);
  const summary = safeObject(value.summary);
  if (summary.item_count === undefined && typeof value.item_count === 'number') summary.item_count = value.item_count;
  if (summary.matched_count === undefined && typeof value.matched_count === 'number') summary.matched_count = value.matched_count;
  if (summary.exception_count === undefined && typeof value.exception_count === 'number') summary.exception_count = value.exception_count;
  return {
    run_id: safeReference(value.run_id) ?? '',
    business_date: safeReference(value.business_date) ?? '',
    run_type: safeReference(value.run_type) ?? '',
    status: normalizeAdminStatus(value.status) as ReconciliationRunProjection['status'],
    cutoff_at: safeTimestamp(value.cutoff_at),
    closed_at: safeTimestamp(value.closed_at),
    source_watermarks: safeObject(value.source_watermarks),
    summary,
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeReconciliationItem(item: unknown): ReconciliationItemProjection {
  const value = record(item);
  const references = record(value.references);
  const amounts = record(value.amounts);
  const reasonCodes = [value.mismatch_code, value.conflict_code]
    .filter((code): code is string => safeReference(code) !== null);
  return {
    item_id: safeReference(value.item_id) ?? '',
    run_id: safeReference(value.run_id) ?? '',
    eslatin_reference: safeReference(value.eslatin_reference ?? references.eslatin),
    provider_reference: safeReference(value.provider_reference ?? references.provider),
    funds_reference: safeReference(value.funds_reference ?? references.funds),
    amount: safeDecimalOrNull(value.amount ?? amounts.expected, 'amount'),
    currency: safeReference(value.currency) ?? '',
    match_status: safeReference(value.match_status ?? value.status) ?? 'unknown',
    reason_codes: safeStringArray(value.reason_codes).concat(reasonCodes),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeReconciliationException(item: unknown): ReconciliationExceptionProjection {
  const value = record(item);
  return {
    exception_id: safeReference(value.exception_id) ?? '',
    item_id: safeReference(value.item_id) ?? '',
    status: normalizeAdminStatus(value.status) as ReconciliationExceptionProjection['status'],
    category: safeReference(value.category ?? value.difference_type) ?? '',
    difference_amount: safeDecimalOrNull(value.difference_amount, 'difference_amount'),
    currency: safeReference(value.currency) ?? 'COP',
    severity: safeReference(value.severity) ?? 'unknown',
    owner: safeReference(value.owner ?? value.owner_ref),
    due_at: safeTimestamp(value.due_at),
    temporary_acceptance_until: safeTimestamp(value.temporary_acceptance_until),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeResolutionIntent(item: unknown): ResolutionIntentProjection {
  const value = record(item);
  return {
    intent_id: safeReference(value.intent_id) ?? '',
    exception_id: safeReference(value.exception_id) ?? '',
    resolution_code: safeReference(value.resolution_code) ?? '',
    reason: typeof value.reason === 'string' ? value.reason : '',
    status: normalizeAdminStatus(value.status),
    initiator: decodeActor(value.initiator),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

function decodeTemporaryAcceptanceRequest(item: unknown): TemporaryAcceptanceRequestProjection {
  const value = record(item);
  return {
    request_id: safeReference(value.request_id) ?? '',
    exception_id: safeReference(value.exception_id) ?? '',
    status: normalizeAdminStatus(value.status),
    reason: typeof value.reason === 'string' ? value.reason : '',
    initiator: decodeActor(value.initiator),
    approver: decodeActor(value.approver),
    expires_at: safeTimestamp(value.expires_at) as string,
    decided_at: safeTimestamp(value.decided_at),
    allowed_actions: safeStringArray(value.allowed_actions),
    version: safeVersion(value.version),
    created_at: safeTimestamp(value.created_at) as string,
    updated_at: safeTimestamp(value.updated_at) as string,
  };
}

const EXPORT_STATUSES = new Set(['queued', 'generating', 'ready', 'downloaded', 'failed', 'expired']);

function decodeReconciliationExport(value: unknown): ReconciliationExportProjection {
  const exportValue = record(value);
  const status = safeReference(exportValue.status);
  if (!status || !EXPORT_STATUSES.has(status)) {
    throw new PayMp002AdminError({
      code: 'RESPONSE_INVALID',
      message: 'Invalid reconciliation export status',
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    });
  }
  return {
    export_id: safeReference(exportValue.export_id) ?? '',
    status: status as ReconciliationExportProjection['status'],
    download_path: exportValue.download_path === null ? null : safeReference(exportValue.download_path),
    expires_at: safeTimestamp(exportValue.expires_at) as string,
    audit_reference: safeReference(exportValue.audit_reference) ?? '',
    version: safeVersion(exportValue.version),
    created_at: safeTimestamp(exportValue.created_at) as string,
    updated_at: safeTimestamp(exportValue.updated_at) as string,
  };
}

function decodeAuditEvent(item: unknown): AuditEventProjection {
  const value = record(item);
  const resource = record(value.resource);
  return {
    event_id: safeReference(value.event_id) ?? '',
    actor: decodeActor(value.actor),
    resource: {
      type: safeReference(resource.type) ?? '',
      id: safeReference(resource.id) ?? '',
    },
    action: safeReference(value.action) ?? '',
    result: safeReference(value.result) ?? 'unknown',
    scope: decodeScope(value.scope),
    reason_code: value.reason_code === null ? null : safeReference(value.reason_code),
    safe_metadata: safeObject(value.safe_metadata),
    occurred_at: safeTimestamp(value.occurred_at) as string,
  };
}

function queryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

async function getP002Page<T>(
  path: string,
  params: Record<string, string | number | undefined>,
  decodeItem: (item: unknown) => T,
  skipTenantId = true,
): Promise<CursorPage<T>> {
  try {
    const response = await apiGet<unknown>(`${P002_BASE}${path}${queryString(params)}`, {
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
      skipTenantId,
    });
    return decodeCursorPage(response, decodeItem);
  } catch (error) {
    throw toCanonicalError(error);
  }
}

export function getRefundCases(params: { status?: string; tenant_scope?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/refund-cases', params, decodeRefundCase);
}

export function getRuntimeRails(params: { axis?: string; scope_type?: string; scope_id?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/runtime-rails', params, decodeRail);
}

export function closeRuntimeRail(
  body: {
    axis: RuntimeRailControlProjection['axis'];
    scope: RuntimeRailControlProjection['scope'];
    reason: string;
    incident_reference: string;
    expected_version: number;
  },
  idempotencyKey: string,
) {
  return postP002Intent<unknown>('/admin/runtime-rails/close-requests', body, idempotencyKey)
    .then((value) => decodeRail(value));
}

export function requestRuntimeRailReopen(
  controlId: string,
  body: { reason: string; health_check_reference: string; expected_version: number },
  idempotencyKey: string,
) {
  return postP002Intent<unknown>(`/admin/runtime-rails/${encodeURIComponent(controlId)}/reopen-requests`, body, idempotencyKey)
    .then((value) => decodeRailReopenRequest(value));
}

export function decideRuntimeRailReopen(
  requestId: string,
  body: { decision: 'approve' | 'reject'; reason: string; expected_version: number },
  idempotencyKey: string,
) {
  return postP002Intent<unknown>(`/admin/runtime-rail-reopen-requests/${encodeURIComponent(requestId)}/decisions`, body, idempotencyKey)
    .then((value) => decodeRailReopenRequest(value));
}

export function getSupportCases(params: { status?: string; category?: string; tenant_scope?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/support-cases', params, decodeSupportCase);
}

export function getChargebackCases(params: { status?: string; deadline_from?: string; deadline_to?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/chargeback-cases', params, decodeChargebackCase, false);
}

export function getReconciliationRuns(params: { business_date?: string; status?: string; tenant_scope?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/reconciliation/runs', params, decodeReconciliationRun);
}

function scopeQuery(path: string, tenantScope?: string): string {
  return tenantScope ? `${path}${path.includes('?') ? '&' : '?'}tenant_scope=${encodeURIComponent(tenantScope)}` : path;
}

async function getP002Resource<T>(path: string, decode: (value: unknown) => T, skipTenantId = true): Promise<T> {
  try {
    const response = await apiGet<unknown>(`${P002_BASE}${path}`, {
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
      skipTenantId,
    });
    return decode(response);
  } catch (error) {
    throw toCanonicalError(error);
  }
}

export function getReconciliationRun(runId: string, tenantScope?: string) {
  return getP002Resource(scopeQuery(`/admin/reconciliation/runs/${encodeURIComponent(runId)}`, tenantScope), (value) => decodeReconciliationRun(value));
}

export function getChargebackCase(caseId: string) {
  return getP002Resource(`/admin/chargeback-cases/${encodeURIComponent(caseId)}`, decodeChargebackCase, false);
}

export function getReconciliationItems(params: { runId: string; status?: string; tenant_scope?: string; cursor?: string; limit?: number }) {
  return getP002Page(
    `/admin/reconciliation/runs/${encodeURIComponent(params.runId)}/items`,
    { status: params.status, cursor: params.cursor, limit: params.limit, tenant_scope: params.tenant_scope },
    decodeReconciliationItem,
  );
}

export function getReconciliationExceptions(params: { status?: string; tenant_scope?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/reconciliation/exceptions', {
    status: params.status,
    cursor: params.cursor,
    limit: params.limit,
    tenant_scope: params.tenant_scope,
  }, decodeReconciliationException);
}

export function getReconciliationExport(exportId: string, tenantScope?: string) {
  return getP002Resource(scopeQuery(`/admin/reconciliation/exports/${encodeURIComponent(exportId)}`, tenantScope), decodeReconciliationExport);
}

export function createReconciliationExport(
  runId: string,
  filters: { status?: string[] },
  idempotencyKey: string,
  tenantScope?: string,
) {
  const path = scopeQuery('/admin/reconciliation/exports', tenantScope);
  return postP002Intent<unknown>(path, { run_id: runId, filters: { status: filters.status ?? [] }, format: 'csv' }, idempotencyKey)
    .then(decodeReconciliationExport);
}

export function createResolutionIntent(
  exceptionId: string,
  body: { resolution_code: string; reason: string; expected_version: number },
  idempotencyKey: string,
  tenantScope?: string,
) {
  return postP002Intent<unknown>(scopeQuery(`/admin/reconciliation/exceptions/${encodeURIComponent(exceptionId)}/resolution-intents`, tenantScope), body, idempotencyKey)
    .then((value) => decodeResolutionIntent(value));
}

export function requestTemporaryAcceptance(
  exceptionId: string,
  body: { reason: string; expected_version: number },
  idempotencyKey: string,
  tenantScope?: string,
) {
  return postP002Intent<unknown>(scopeQuery(`/admin/reconciliation/exceptions/${encodeURIComponent(exceptionId)}/temporary-acceptance-requests`, tenantScope), body, idempotencyKey)
    .then((value) => decodeTemporaryAcceptanceRequest(value));
}

export function decideTemporaryAcceptance(
  requestId: string,
  body: { decision: 'approve' | 'reject'; reason: string; expected_version: number },
  idempotencyKey: string,
  tenantScope?: string,
) {
  return postP002Intent<unknown>(scopeQuery(`/admin/reconciliation/temporary-acceptance-requests/${encodeURIComponent(requestId)}/decisions`, tenantScope), body, idempotencyKey)
    .then((value) => decodeTemporaryAcceptanceRequest(value));
}

export function safeReconciliationDownloadPath(path: string | null): string | null {
  if (!path || !/^\/api\/v1\/admin\/reconciliation\/exports\/[^/]+\/download$/.test(path)) return null;
  return path;
}

export function reconciliationCsvFilename(exportId: string): string {
  const safeId = exportId.replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80) || 'export';
  return `reconciliation-${safeId}.csv`;
}

export function getAuditEvents(params: { actor?: string; resource_type?: string; resource_id?: string; action?: string; result?: string; from?: string; to?: string; cursor?: string; limit?: number } = {}) {
  return getP002Page('/admin/audit-events', params, decodeAuditEvent, false);
}

export async function postP002Intent<T>(
  path: string,
  body: unknown,
  idempotencyKey: string,
): Promise<T> {
  if (!idempotencyKey.trim()) {
    throw new PayMp002AdminError({
      code: 'REQUEST_INVALID',
      message: 'An idempotency key is required',
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    }, 422);
  }
  try {
    return await apiPost<T>(`${P002_BASE}${path}`, body, {
      headers: { Accept: PAY_MP_002_MEDIA_TYPE, 'Idempotency-Key': idempotencyKey },
      skipTenantId: true,
    });
  } catch (error) {
    throw toCanonicalError(error);
  }
}

export { PAY_MP_002_MEDIA_TYPE };
