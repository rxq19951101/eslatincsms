import axios from 'axios';

import apiClient from '../../api/client';
import { API_ENDPOINTS } from '../../constants/config';
import {
  normalizeAllocationStatus,
  normalizeEligibilityStatus,
  normalizeRecoveryStatus,
} from './status';
import type {
  CanonicalError,
  CursorPage,
  FinancialEligibilityProjection,
  P001TransactionProjection,
  P002InvoiceProjection,
  P002PaymentFact,
  P002TransactionProjection,
  P002TimelineItem,
  SupportCaseProjection,
  SupportCaseStatus,
  SupportCaseTimelineItem,
  PaymentAllocationProjection,
  RecoveryAttemptProjection,
  RecoveryNextAction,
  RecoveryMethod,
  RecoveryMethodOption,
  RecoveryTimelineItem,
  SavedPaymentMethodRef,
  UnpaidInvoiceDetail,
  UnpaidInvoiceProjection,
} from './types';
import { PAY_MP_002_MEDIA_TYPE } from './types';

const DECIMAL_STRING = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;
const MAX_REFERENCE_LENGTH = 256;

export class PayMp002Error extends Error {
  constructor(
    public readonly canonical: CanonicalError,
    public readonly httpStatus?: number,
  ) {
    super(canonical.message);
    this.name = 'PayMp002Error';
  }
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function safeString(value: unknown): string | null {
  return typeof value === 'string' && value.length <= MAX_REFERENCE_LENGTH ? value : null;
}

function invalidProjection(field: string): never {
  throw new PayMp002Error({
    code: 'RESPONSE_INVALID',
    message: `Invalid ${field} projection`,
    reference: null,
    retryable: false,
    retry_after_seconds: null,
  });
}

function hasOwn(value: Record<string, unknown>, field: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, field);
}

function required(value: Record<string, unknown>, field: string): unknown {
  if (!hasOwn(value, field)) invalidProjection(field);
  return value[field];
}

function requiredOpaqueString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > MAX_REFERENCE_LENGTH) {
    return invalidProjection(field);
  }
  return value;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) return invalidProjection(field);
  return value;
}

function requiredNullableString(value: unknown, field: string): string | null {
  if (value === null) return null;
  if (typeof value !== 'string') return invalidProjection(field);
  return value;
}

function requiredSafeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) return invalidProjection(field);
  return value;
}

function requiredNullableDecimal(value: unknown, field: string): string | null {
  if (value === null) return null;
  assertDecimal(value, field);
  return value;
}

function requiredUtcTimestamp(value: unknown, field: string): string {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value)) || !/(?:Z|[+-]00:00)$/.test(value)) {
    return invalidProjection(field);
  }
  return value;
}

function requiredPositiveInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) {
    return invalidProjection(field);
  }
  return value;
}

function requiredNullableOpaqueString(value: unknown, field: string): string | null {
  if (value === null) return null;
  return requiredOpaqueString(value, field);
}

function requiredNullableUtcTimestamp(value: unknown, field: string): string | null {
  if (value === null) return null;
  return requiredUtcTimestamp(value, field);
}

function normalizeRecoveryNextAction(payload: unknown): RecoveryNextAction {
  const value = record(payload);
  const type = required(value, 'type');
  if (type !== 'none' && type !== 'poll' && type !== 'open_checkout' &&
      type !== 'open_provider_url' && type !== 'contact_support') {
    return invalidProjection('next_action.type');
  }

  const action: RecoveryNextAction = { type };
  if (hasOwn(value, 'checkout_session_id')) {
    action.checkout_session_id = requiredNullableOpaqueString(
      value.checkout_session_id,
      'next_action.checkout_session_id',
    );
  }
  if (hasOwn(value, 'url')) {
    if (value.url !== null && typeof value.url !== 'string') {
      return invalidProjection('next_action.url');
    }
    action.url = value.url;
  }
  if (hasOwn(value, 'expires_at')) {
    action.expires_at = requiredNullableUtcTimestamp(value.expires_at, 'next_action.expires_at');
  }
  if (hasOwn(value, 'poll_after_seconds')) {
    if (value.poll_after_seconds !== null &&
        (typeof value.poll_after_seconds !== 'number' ||
          !Number.isSafeInteger(value.poll_after_seconds) || value.poll_after_seconds < 0)) {
      return invalidProjection('next_action.poll_after_seconds');
    }
    action.poll_after_seconds = value.poll_after_seconds;
  }
  return action;
}

function normalizeFinancialEligibilityProjection(payload: unknown): FinancialEligibilityProjection {
  const value = record(payload);
  const statusValue = required(value, 'status');
  const reasonCodesValue = required(value, 'reason_codes');
  const evaluatedAt = requiredUtcTimestamp(
    required(value, 'evaluated_at'),
    'financial_eligibility.evaluated_at',
  );
  const version = requiredPositiveInteger(
    required(value, 'version'),
    'financial_eligibility.version',
  );
  if (!Array.isArray(reasonCodesValue) ||
      !reasonCodesValue.every((reason): reason is string => typeof reason === 'string')) {
    return invalidProjection('financial_eligibility.reason_codes');
  }
  if (reasonCodesValue.includes('rail_closed')) {
    return invalidProjection('financial_eligibility.reason_codes');
  }
  return {
    status: normalizeEligibilityStatus(statusValue),
    reason_codes: [...reasonCodesValue],
    evaluated_at: evaluatedAt,
    version,
  };
}

function canonicalErrorFromPayload(payload: unknown, status: number): CanonicalError {
  const body = record(payload);
  const envelope = record(body.error);
  const code = typeof envelope.code === 'string'
    ? envelope.code
    : typeof body.code === 'string' ? body.code : `HTTP_${status}`;
  const message = typeof envelope.message === 'string'
    ? envelope.message
    : typeof body.message === 'string' ? body.message : 'The request could not be completed';
  const retryAfter = envelope.retry_after_seconds;
  return {
    code,
    message,
    reference: safeString(envelope.reference ?? body.reference),
    retryable: envelope.retryable === true,
    retry_after_seconds: typeof retryAfter === 'number' && Number.isFinite(retryAfter)
      ? retryAfter
      : null,
    ...(typeof envelope.current_version === 'number' ? { current_version: envelope.current_version } : {}),
  };
}

function toPayMp002Error(error: unknown): PayMp002Error {
  if (error instanceof PayMp002Error) return error;
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return new PayMp002Error({
        code: 'NETWORK_ERROR',
        message: 'The request could not be completed',
        reference: null,
        retryable: true,
        retry_after_seconds: null,
      });
    }
    const status = error.response?.status ?? 0;
    return new PayMp002Error(canonicalErrorFromPayload(error.response?.data, status), status);
  }
  return new PayMp002Error({
    code: 'NETWORK_ERROR',
    message: 'The request could not be completed',
    reference: null,
    retryable: true,
    retry_after_seconds: null,
  });
}

function assertDecimal(value: unknown, field: string): asserts value is string {
  if (typeof value !== 'string' || !DECIMAL_STRING.test(value)) {
    throw new PayMp002Error({
      code: 'RESPONSE_INVALID',
      message: `Invalid ${field} projection`,
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    });
  }
}

function decodeCursorPage<T>(payload: unknown, decodeItem: (item: unknown) => T): CursorPage<T> {
  const body = record(payload);
  const page = record(body.page);
  if (!Array.isArray(body.items) ||
      !(typeof page.next_cursor === 'string' || page.next_cursor === null) ||
      typeof page.has_more !== 'boolean') {
    throw new PayMp002Error({
      code: 'RESPONSE_INVALID',
      message: 'Invalid cursor page projection',
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    });
  }
  return {
    items: body.items.map(decodeItem),
    page: { next_cursor: page.next_cursor, has_more: page.has_more },
  };
}

function enumValue<T extends string>(value: unknown, field: string, allowed: readonly T[]): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) return invalidProjection(field);
  return value as T;
}

function decodeP002Invoice(item: unknown): P002InvoiceProjection {
  const value = record(item);
  return {
    id: requiredOpaqueString(required(value, 'id'), 'invoice.id'),
    reference: requiredString(required(value, 'reference'), 'invoice.reference'),
    status: enumValue(
      required(value, 'status'),
      'invoice.status',
      ['pending', 'paid', 'cancelled', 'refunded', 'unknown'] as const,
    ),
    amount: requiredNullableDecimal(required(value, 'amount'), 'invoice.amount'),
    currency: requiredOpaqueString(required(value, 'currency'), 'invoice.currency'),
    issued_at: requiredNullableUtcTimestamp(required(value, 'issued_at'), 'invoice.issued_at'),
    paid_at: requiredNullableUtcTimestamp(required(value, 'paid_at'), 'invoice.paid_at'),
    pricing_snapshot_reference: requiredNullableOpaqueString(
      required(value, 'pricing_snapshot_reference'),
      'invoice.pricing_snapshot_reference',
    ),
  };
}

function decodeP002Payment(item: unknown): P002PaymentFact {
  const value = record(item);
  return {
    id: requiredOpaqueString(required(value, 'id'), 'payment.id'),
    reference: requiredString(required(value, 'reference'), 'payment.reference'),
    status: enumValue(
      required(value, 'status'),
      'payment.status',
      ['paid', 'processing', 'unpaid', 'refunded', 'unknown'] as const,
    ),
    method: requiredNullableString(required(value, 'method'), 'payment.method'),
    amount: requiredNullableDecimal(required(value, 'amount'), 'payment.amount'),
    currency: requiredOpaqueString(required(value, 'currency'), 'payment.currency'),
    occurred_at: requiredNullableUtcTimestamp(required(value, 'occurred_at'), 'payment.occurred_at'),
    updated_at: requiredNullableUtcTimestamp(required(value, 'updated_at'), 'payment.updated_at'),
  };
}

function decodeP002TimelineItem(item: unknown): P002TimelineItem {
  const value = record(item);
  return {
    event_id: requiredOpaqueString(required(value, 'event_id'), 'timeline.event_id'),
    type: requiredString(required(value, 'type'), 'timeline.type'),
    status: requiredString(required(value, 'status'), 'timeline.status'),
    occurred_at: requiredUtcTimestamp(required(value, 'occurred_at'), 'timeline.occurred_at'),
    actor: requiredNullableString(required(value, 'actor'), 'timeline.actor'),
    reason_code: requiredNullableString(required(value, 'reason_code'), 'timeline.reason_code'),
    reference: requiredString(required(value, 'reference'), 'timeline.reference'),
  };
}

function normalizeSupportStatus(value: unknown, field: string): SupportCaseStatus {
  if (typeof value !== 'string') return invalidProjection(field);
  return ['open', 'acknowledged', 'in_progress', 'waiting_user', 'resolved', 'closed'].includes(value)
    ? value as SupportCaseStatus
    : 'unknown';
}

function decodeSupportActor(item: unknown, field: string) {
  const value = record(item);
  return {
    id: requiredOpaqueString(required(value, 'id'), `${field}.id`),
    display_name: requiredString(required(value, 'display_name'), `${field}.display_name`),
    role_label: requiredString(required(value, 'role_label'), `${field}.role_label`),
  };
}

function decodeSupportTimelineItem(item: unknown): SupportCaseTimelineItem {
  const value = record(item);
  return {
    event_id: requiredOpaqueString(required(value, 'event_id'), 'support.timeline.event_id'),
    case_id: requiredOpaqueString(required(value, 'case_id'), 'support.timeline.case_id'),
    event_type: requiredString(required(value, 'event_type'), 'support.timeline.event_type'),
    note_visibility: requiredString(required(value, 'note_visibility'), 'support.timeline.note_visibility'),
    status: normalizeSupportStatus(value.status, 'support.timeline.status'),
    actor: decodeSupportActor(required(value, 'actor'), 'support.timeline.actor'),
    occurred_at: requiredUtcTimestamp(required(value, 'occurred_at'), 'support.timeline.occurred_at'),
    case_version: requiredPositiveInteger(required(value, 'case_version'), 'support.timeline.case_version'),
  };
}

function decodeSupportCase(item: unknown): SupportCaseProjection {
  const value = record(item);
  const resources = required(value, 'linked_resources');
  const timeline = required(value, 'timeline');
  const actions = required(value, 'allowed_actions');
  if (!Array.isArray(resources) || !Array.isArray(timeline) || !Array.isArray(actions) ||
      !actions.every((action): action is string => typeof action === 'string' && action.length > 0 && action.length <= MAX_REFERENCE_LENGTH)) {
    return invalidProjection('support collections');
  }
  const decodedResources = resources.map((item) => {
    const resource = record(item);
    return {
      type: requiredString(required(resource, 'type'), 'linked_resources.type'),
      id: requiredOpaqueString(required(resource, 'id'), 'linked_resources.id'),
      reference: requiredNullableString(required(resource, 'reference'), 'linked_resources.reference'),
    };
  });
  const result: SupportCaseProjection = {
    case_id: requiredOpaqueString(required(value, 'case_id'), 'case_id'),
    reference: requiredString(required(value, 'reference'), 'reference'),
    status: normalizeSupportStatus(value.status, 'status'),
    category: requiredString(required(value, 'category'), 'category'),
    linked_resources: decodedResources,
    sla_target_at: requiredNullableUtcTimestamp(required(value, 'sla_target_at'), 'sla_target_at'),
    assignee: value.assignee === null ? null : decodeSupportActor(required(value, 'assignee'), 'assignee'),
    timeline: timeline.map(decodeSupportTimelineItem),
    allowed_actions: [...actions],
    version: requiredPositiveInteger(required(value, 'version'), 'version'),
    created_at: requiredUtcTimestamp(required(value, 'created_at'), 'created_at'),
    updated_at: requiredUtcTimestamp(required(value, 'updated_at'), 'updated_at'),
  };
  if (hasOwn(value, 'linked_refund_case')) {
    const linked = value.linked_refund_case;
    if (linked === null) result.linked_refund_case = null;
    else {
      const resource = record(linked);
      result.linked_refund_case = {
        type: requiredString(required(resource, 'type'), 'linked_refund_case.type'),
        id: requiredOpaqueString(required(resource, 'id'), 'linked_refund_case.id'),
        reference: requiredNullableString(required(resource, 'reference'), 'linked_refund_case.reference'),
      };
    }
  }
  return result;
}

function decodeP002Transaction(item: unknown): P002TransactionProjection {
  const value = record(item);
  const id = requiredOpaqueString(required(value, 'id'), 'id');
  const transactionId = requiredSafeInteger(required(value, 'transaction_id'), 'transaction_id');
  const chargePointId = requiredOpaqueString(required(value, 'charge_point_id'), 'charge_point_id');
  const ocppIdentity = requiredNullableString(required(value, 'ocpp_identity'), 'ocpp_identity');
  const evseId = requiredOpaqueString(required(value, 'evse_id'), 'evse_id');
  const startTime = requiredNullableUtcTimestamp(required(value, 'start_time'), 'start_time');
  const endTime = requiredNullableUtcTimestamp(required(value, 'end_time'), 'end_time');
  const status = requiredString(required(value, 'status'), 'status');
  const energyKwh = requiredNullableDecimal(required(value, 'energy_kwh'), 'energy_kwh');
  const durationMinutes = requiredNullableDecimal(required(value, 'duration_minutes'), 'duration_minutes');
  const siteName = requiredNullableString(required(value, 'site_name'), 'site_name');
  const siteAddress = requiredNullableString(required(value, 'site_address'), 'site_address');
  const result: P002TransactionProjection = {
    id,
    transaction_id: transactionId,
    charge_point_id: chargePointId,
    ocpp_identity: ocppIdentity,
    evse_id: evseId,
    start_time: startTime,
    end_time: endTime,
    status,
    energy_kwh: energyKwh,
    duration_minutes: durationMinutes,
    site_name: siteName,
    site_address: siteAddress,
  };

  if (hasOwn(value, 'session')) {
    const session = record(value.session);
    result.session = {
      id: requiredOpaqueString(required(session, 'id'), 'session.id'),
      reference: requiredString(required(session, 'reference'), 'session.reference'),
      status: requiredString(required(session, 'status'), 'session.status'),
      started_at: requiredNullableUtcTimestamp(required(session, 'started_at'), 'session.started_at'),
      ended_at: requiredNullableUtcTimestamp(required(session, 'ended_at'), 'session.ended_at'),
    };
  }
  if (hasOwn(value, 'invoice')) {
    result.invoice = value.invoice === null ? null : decodeP002Invoice(value.invoice);
  }
  if (hasOwn(value, 'payments')) {
    if (!Array.isArray(value.payments)) return invalidProjection('payments');
    result.payments = value.payments.map(decodeP002Payment);
  }
  if (hasOwn(value, 'payment_status')) {
    result.payment_status = enumValue(
      value.payment_status,
      'payment_status',
      ['paid', 'processing', 'unpaid', 'refunded', 'partially_refunded', 'disputed', 'unknown'] as const,
    );
  }
  if (hasOwn(value, 'data_quality')) {
    result.data_quality = enumValue(value.data_quality, 'data_quality', ['current', 'legacy', 'unknown'] as const);
  }
  if (hasOwn(value, 'support_case_refs')) {
    if (!Array.isArray(value.support_case_refs) ||
        !value.support_case_refs.every((ref): ref is string => typeof ref === 'string' && ref.length <= MAX_REFERENCE_LENGTH)) {
      return invalidProjection('support_case_refs');
    }
    result.support_case_refs = [...value.support_case_refs];
  }
  if (hasOwn(value, 'allowed_actions')) {
    if (!Array.isArray(value.allowed_actions) ||
        !value.allowed_actions.every((action): action is string => typeof action === 'string' && action.length > 0 && action.length <= MAX_REFERENCE_LENGTH)) {
      return invalidProjection('allowed_actions');
    }
    result.allowed_actions = [...value.allowed_actions];
  }
  if (hasOwn(value, 'updated_at')) {
    result.updated_at = requiredUtcTimestamp(value.updated_at, 'updated_at');
  }
  if (hasOwn(value, 'meter_start')) {
    if (value.meter_start !== null && (typeof value.meter_start !== 'number' || !Number.isSafeInteger(value.meter_start))) {
      return invalidProjection('meter_start');
    }
    result.meter_start = value.meter_start;
  }
  if (hasOwn(value, 'meter_stop')) {
    if (value.meter_stop !== null && (typeof value.meter_stop !== 'number' || !Number.isSafeInteger(value.meter_stop))) {
      return invalidProjection('meter_stop');
    }
    result.meter_stop = value.meter_stop;
  }
  if (hasOwn(value, 'invoice_number')) {
    result.invoice_number = requiredNullableString(value.invoice_number, 'invoice_number');
  }
  if (hasOwn(value, 'total_amount')) {
    result.total_amount = requiredNullableDecimal(value.total_amount, 'total_amount');
  }
  if (hasOwn(value, 'currency')) {
    result.currency = requiredOpaqueString(value.currency, 'currency');
  }
  if (hasOwn(value, 'billing_status')) {
    result.billing_status = value.billing_status === null
      ? null
      : enumValue(value.billing_status, 'billing_status', ['pending', 'paid', 'cancelled', 'refunded', 'unknown'] as const);
  }
  if (hasOwn(value, 'connector_number')) {
    if (value.connector_number !== null && (typeof value.connector_number !== 'number' || !Number.isSafeInteger(value.connector_number))) {
      return invalidProjection('connector_number');
    }
    result.connector_number = value.connector_number;
  }
  if (hasOwn(value, 'connector_label')) {
    result.connector_label = requiredNullableString(value.connector_label, 'connector_label');
  }
  if (hasOwn(value, 'charge_point_label')) {
    result.charge_point_label = requiredNullableString(value.charge_point_label, 'charge_point_label');
  }
  if (hasOwn(value, 'timeline')) {
    if (!Array.isArray(value.timeline)) return invalidProjection('timeline');
    result.timeline = value.timeline.map(decodeP002TimelineItem);
  }
  return result;
}

function decodeRecoveryMethodOption(item: unknown): RecoveryMethodOption {
  const value = record(item);
  const method = required(value, 'method');
  if (method !== 'wallet' && method !== 'new_card' && method !== 'saved_card') {
    return invalidProjection('available_methods.method');
  }
  const enabled = required(value, 'enabled');
  if (typeof enabled !== 'boolean') return invalidProjection('available_methods.enabled');
  const disabledReason = requiredNullableString(
    required(value, 'disabled_reason_code'),
    'available_methods.disabled_reason_code',
  );
  const result: RecoveryMethodOption = {
    method,
    enabled,
    disabled_reason_code: disabledReason,
  };
  if (hasOwn(value, 'saved_payment_method_ref')) {
    const saved = record(value.saved_payment_method_ref);
    const ref: SavedPaymentMethodRef = {
      id: requiredOpaqueString(required(saved, 'id'), 'saved_payment_method_ref.id'),
      brand: requiredString(required(saved, 'brand'), 'saved_payment_method_ref.brand'),
      last_four: requiredString(required(saved, 'last_four'), 'saved_payment_method_ref.last_four'),
      is_default: (() => {
        const isDefault = required(saved, 'is_default');
        if (typeof isDefault !== 'boolean') return invalidProjection('saved_payment_method_ref.is_default');
        return isDefault;
      })(),
    };
    result.saved_payment_method_ref = ref;
  }
  if (method === 'saved_card' && !result.saved_payment_method_ref) {
    return invalidProjection('available_methods.saved_payment_method_ref');
  }
  return result;
}

function decodeUnpaidInvoice(item: unknown): UnpaidInvoiceProjection {
  const value = record(item);
  const connector = required(value, 'connector_id');
  if (connector !== null && (typeof connector !== 'number' || !Number.isSafeInteger(connector))) {
    return invalidProjection('connector_id');
  }
  const d1Status = required(value, 'd1_status');
  if (d1Status !== 'blocked') return invalidProjection('d1_status');
  const actions = required(value, 'allowed_actions');
  if (!Array.isArray(actions) || !actions.every((action): action is string =>
    typeof action === 'string' && action.length > 0 && action.length <= MAX_REFERENCE_LENGTH)) {
    return invalidProjection('allowed_actions');
  }
  const decimals = ['energy_kwh', 'original_amount', 'allocated_amount', 'refunded_amount', 'outstanding_amount'] as const;
  const decodedDecimals = Object.fromEntries(decimals.map((field) => {
    const amount = required(value, field);
    assertDecimal(amount, field);
    return [field, amount];
  })) as Record<typeof decimals[number], string>;
  return {
    invoice_id: requiredOpaqueString(required(value, 'invoice_id'), 'invoice_id'),
    invoice_reference: requiredString(required(value, 'invoice_reference'), 'invoice_reference'),
    session_id: requiredOpaqueString(required(value, 'session_id'), 'session_id'),
    site: requiredNullableString(required(value, 'site'), 'site'),
    charge_point_reference: requiredNullableString(
      required(value, 'charge_point_reference'),
      'charge_point_reference',
    ),
    connector_id: connector,
    started_at: requiredNullableUtcTimestamp(required(value, 'started_at'), 'started_at'),
    ended_at: requiredNullableUtcTimestamp(required(value, 'ended_at'), 'ended_at'),
    ...decodedDecimals,
    currency: requiredOpaqueString(required(value, 'currency'), 'currency'),
    blocking_reason: requiredString(required(value, 'blocking_reason'), 'blocking_reason'),
    recovery_status: requiredNullableString(required(value, 'recovery_status'), 'recovery_status'),
    active_recovery_attempt_id: requiredNullableOpaqueString(
      required(value, 'active_recovery_attempt_id'),
      'active_recovery_attempt_id',
    ),
    d1_status: d1Status,
    allowed_actions: [...actions],
    updated_at: requiredUtcTimestamp(required(value, 'updated_at'), 'updated_at'),
  };
}

function decodeUnpaidInvoiceDetail(payload: unknown): UnpaidInvoiceDetail {
  const value = record(payload);
  const summary = decodeUnpaidInvoice(payload);
  const methodsValue = required(value, 'available_methods');
  if (!Array.isArray(methodsValue)) return invalidProjection('available_methods');
  const activeValue = required(value, 'active_recovery_attempt');
  const timelineValue = required(value, 'timeline');
  const supportRefsValue = required(value, 'support_case_refs');
  if (!Array.isArray(timelineValue) || !Array.isArray(supportRefsValue) ||
      !supportRefsValue.every((ref): ref is string => typeof ref === 'string')) {
    return invalidProjection('detail collections');
  }
  const timeline: RecoveryTimelineItem[] = timelineValue.map((item) => {
    const entry = record(item);
    return {
      type: requiredString(required(entry, 'type'), 'timeline.type'),
      status: requiredString(required(entry, 'status'), 'timeline.status'),
      occurred_at: requiredNullableUtcTimestamp(required(entry, 'occurred_at'), 'timeline.occurred_at'),
      reference: requiredNullableString(required(entry, 'reference'), 'timeline.reference'),
    };
  });
  return {
    ...summary,
    available_methods: methodsValue.map(decodeRecoveryMethodOption),
    active_recovery_attempt: activeValue === null ? null : normalizeRecoveryAttempt(activeValue),
    timeline,
    financial_eligibility: normalizeFinancialEligibilityProjection(
      required(value, 'financial_eligibility'),
    ),
    support_case_refs: [...supportRefsValue],
  };
}

export function normalizeRecoveryAttempt(payload: unknown): RecoveryAttemptProjection {
  const value = record(payload);
  const attemptId = requiredOpaqueString(required(value, 'attempt_id'), 'attempt_id');
  const invoiceId = requiredOpaqueString(required(value, 'invoice_id'), 'invoice_id');
  const targetAmount = required(value, 'target_amount');
  assertDecimal(targetAmount, 'target_amount');
  const currency = requiredOpaqueString(required(value, 'currency'), 'currency');
  const methodValue = required(value, 'method');
  if (methodValue !== 'wallet' && methodValue !== 'new_card' && methodValue !== 'saved_card') {
    return invalidProjection('method');
  }
  const rawStatus = required(value, 'status');
  const status = normalizeRecoveryStatus(value.status);
  const allocationPayload = required(value, 'allocation');
  const allocationValue = allocationPayload === null ? null : record(allocationPayload);
  const allocation: PaymentAllocationProjection | null = allocationValue === null
    ? null
    : {
      status: normalizeAllocationStatus(required(allocationValue, 'status')),
      amount: (() => {
        const amount = required(allocationValue, 'amount');
        assertDecimal(amount, 'allocation.amount');
        return amount;
      })(),
      confirmed_at: requiredNullableUtcTimestamp(
        required(allocationValue, 'confirmed_at'),
        'allocation.confirmed_at',
      ),
    };
  const financialEligibility = normalizeFinancialEligibilityProjection(
    required(value, 'financial_eligibility'),
  );
  const nextAction = normalizeRecoveryNextAction(required(value, 'next_action'));
  const supportReferenceValue = required(value, 'support_reference');
  if (supportReferenceValue !== null && typeof supportReferenceValue !== 'string') {
    return invalidProjection('support_reference');
  }
  const allowedActionsValue = required(value, 'allowed_actions');
  if (!Array.isArray(allowedActionsValue) ||
      !allowedActionsValue.every((action): action is string => typeof action === 'string' && action.length <= MAX_REFERENCE_LENGTH)) {
    return invalidProjection('allowed_actions');
  }
  const paymentOrderId = requiredNullableOpaqueString(
    required(value, 'payment_order_id'),
    'payment_order_id',
  );
  const version = requiredPositiveInteger(required(value, 'version'), 'version');
  const createdAt = requiredUtcTimestamp(required(value, 'created_at'), 'created_at');
  const updatedAt = requiredUtcTimestamp(required(value, 'updated_at'), 'updated_at');
  const isDuplicateApproval = value.reason_code === 'duplicate_approval' || rawStatus === 'duplicate_approved';
  const reasonCode = hasOwn(value, 'reason_code')
    ? value.reason_code === null ? null : requiredOpaqueString(value.reason_code, 'reason_code')
    : undefined;
  return {
    attempt_id: attemptId,
    invoice_id: invoiceId,
    target_amount: targetAmount,
    currency,
    method: methodValue,
    status: isDuplicateApproval ? 'manual_review' : status,
    ...(isDuplicateApproval || reasonCode !== undefined
      ? { reason_code: isDuplicateApproval ? 'duplicate_approval' : reasonCode }
      : {}),
    payment_order_id: paymentOrderId,
    allocation: isDuplicateApproval ? null : allocation,
    financial_eligibility: financialEligibility,
    next_action: nextAction,
    support_reference: supportReferenceValue === null ? null : requiredOpaqueString(supportReferenceValue, 'support_reference'),
    allowed_actions: [...allowedActionsValue],
    version,
    created_at: createdAt,
    updated_at: updatedAt,
  };
}

export function normalizeFinancialEligibility(payload: unknown): FinancialEligibilityProjection {
  return normalizeFinancialEligibilityProjection(payload);
}

export function isAllowedHostedUrl(
  value: unknown,
  options: { sameOrigin: string; allowedHosts: readonly string[] },
): value is string {
  if (typeof value !== 'string' || value.length === 0 || value.length > 2048) return false;
  try {
    const url = new URL(value, options.sameOrigin);
    const base = new URL(options.sameOrigin);
    if (url.origin === base.origin) return url.protocol === 'http:' || url.protocol === 'https:';
    return url.protocol === 'https:' && options.allowedHosts.includes(url.hostname);
  } catch {
    return false;
  }
}

export function getP001Transactions(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<P001TransactionProjection[]> {
  return apiClient.get<P001TransactionProjection[]>(API_ENDPOINTS.TRANSACTIONS.LIST, { params })
    .then((response) => response.data)
    .catch((error: unknown) => { throw toPayMp002Error(error); });
}

export async function getP002Transactions(params: {
  status?: string;
  cursor?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<CursorPage<P002TransactionProjection>> {
  if ('offset' in params && params.offset !== undefined) {
    throw new PayMp002Error({
      code: 'PAGINATION_MODE_INVALID',
      message: 'P002 cursor requests cannot include offset',
      reference: null,
      retryable: false,
      retry_after_seconds: null,
    }, 400);
  }
  try {
    const response = await apiClient.get(API_ENDPOINTS.TRANSACTIONS.LIST, {
      params: { status: params.status, cursor: params.cursor, limit: params.limit },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
    return decodeCursorPage(response.data, decodeP002Transaction);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getP002TransactionDetail(
  sessionId: string,
): Promise<P002TransactionProjection> {
  try {
    const response = await apiClient.get(
      `${API_ENDPOINTS.TRANSACTIONS.DETAIL(encodeURIComponent(sessionId))}`,
      { headers: { Accept: PAY_MP_002_MEDIA_TYPE } },
    );
    return decodeP002Transaction(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getSupportCases(params: {
  status?: string;
  cursor?: string;
  limit?: number;
} = {}): Promise<CursorPage<SupportCaseProjection>> {
  try {
    const response = await apiClient.get('/api/v1/app/support-cases', {
      params: { status: params.status, cursor: params.cursor, limit: params.limit },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
    return decodeCursorPage(response.data, decodeSupportCase);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getSupportCase(caseId: string): Promise<SupportCaseProjection> {
  try {
    const response = await apiClient.get(
      `/api/v1/app/support-cases/${encodeURIComponent(caseId)}`,
      { headers: { Accept: PAY_MP_002_MEDIA_TYPE } },
    );
    return decodeSupportCase(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function createSupportCase(input: {
  category: 'payment_recovery' | 'refund_request' | 'chargeback_question' | 'charging_issue' | 'other';
  resource_type: 'invoice' | 'session' | 'payment' | 'payment_order' | 'recovery_attempt' | 'refund' | 'refund_case' | 'chargeback' | 'chargeback_case';
  resource_id: string;
  description?: string;
}): Promise<SupportCaseProjection> {
  try {
    const response = await apiClient.post(
      '/api/v1/app/support-cases',
      {
        category: input.category,
        context: { resource_type: input.resource_type, resource_id: input.resource_id },
        ...(input.description ? { description: input.description } : {}),
      },
      { headers: { Accept: PAY_MP_002_MEDIA_TYPE } },
    );
    return decodeSupportCase(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getRecoveryAttempt(attemptId: string): Promise<RecoveryAttemptProjection> {
  try {
    const response = await apiClient.get(`/api/v1/app/recovery-attempts/${encodeURIComponent(attemptId)}`);
    return normalizeRecoveryAttempt(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getUnpaidInvoices(params: {
  cursor?: string;
  limit?: number;
} = {}): Promise<CursorPage<UnpaidInvoiceProjection>> {
  try {
    const response = await apiClient.get('/api/v1/app/unpaid-charges', {
      params: { cursor: params.cursor, limit: params.limit },
      headers: { Accept: PAY_MP_002_MEDIA_TYPE },
    });
    return decodeCursorPage(response.data, decodeUnpaidInvoice);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function getUnpaidInvoice(invoiceId: string): Promise<UnpaidInvoiceDetail> {
  try {
    const response = await apiClient.get(
      `/api/v1/app/unpaid-charges/${encodeURIComponent(invoiceId)}`,
      { headers: { Accept: PAY_MP_002_MEDIA_TYPE } },
    );
    return decodeUnpaidInvoiceDetail(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export async function createRecoveryAttempt(
  invoiceId: string,
  method: RecoveryMethod,
  idempotencyKey: string,
  savedPaymentMethodId: string | null = null,
): Promise<RecoveryAttemptProjection> {
  try {
    const response = await apiClient.post(
      `/api/v1/app/unpaid-charges/${encodeURIComponent(invoiceId)}/recovery-attempts`,
      { method, saved_payment_method_id: method === 'saved_card' ? savedPaymentMethodId : null },
      { headers: { 'Idempotency-Key': idempotencyKey } },
    );
    return normalizeRecoveryAttempt(response.data);
  } catch (error) {
    throw toPayMp002Error(error);
  }
}

export { PAY_MP_002_MEDIA_TYPE };
