import type { AdminUser, Tenant } from '@/types';
import type { CanonicalError } from './payMp002Types';

export const PAY_MP_002_PERMISSIONS = [
  'payment.read',
  'refund.request',
  'refund.approve',
  'chargeback.read',
  'reconciliation.read',
  'reconciliation.resolve',
  'reconciliation.exception.request',
  'reconciliation.exception.approve',
  'support.manage',
  'rail.read',
  'rail.close',
  'rail.reopen.request',
  'rail.reopen.approve',
  'audit.read',
] as const;

export type PayMp002Permission = (typeof PAY_MP_002_PERMISSIONS)[number];

export type PayMp002Resource =
  | 'refunds'
  | 'chargebacks'
  | 'reconciliation'
  | 'support'
  | 'rails'
  | 'audit';

export interface PayMp002NavigationItem {
  resource: PayMp002Resource;
  href: `/payments-operations/${PayMp002Resource}`;
  labelKey: string;
  permission: PayMp002Permission;
  descriptionKey: string;
}

export const PAY_MP_002_NAVIGATION: readonly PayMp002NavigationItem[] = [
  {
    resource: 'refunds',
    href: '/payments-operations/refunds',
    labelKey: 'payMp002.nav.refunds',
    permission: 'payment.read',
    descriptionKey: 'payMp002.nav.refundsDescription',
  },
  {
    resource: 'chargebacks',
    href: '/payments-operations/chargebacks',
    labelKey: 'payMp002.nav.chargebacks',
    permission: 'chargeback.read',
    descriptionKey: 'payMp002.nav.chargebacksDescription',
  },
  {
    resource: 'reconciliation',
    href: '/payments-operations/reconciliation',
    labelKey: 'payMp002.nav.reconciliation',
    permission: 'reconciliation.read',
    descriptionKey: 'payMp002.nav.reconciliationDescription',
  },
  {
    resource: 'support',
    href: '/payments-operations/support',
    labelKey: 'payMp002.nav.support',
    permission: 'support.manage',
    descriptionKey: 'payMp002.nav.supportDescription',
  },
  {
    resource: 'rails',
    href: '/payments-operations/rails',
    labelKey: 'payMp002.nav.rails',
    permission: 'rail.read',
    descriptionKey: 'payMp002.nav.railsDescription',
  },
  {
    resource: 'audit',
    href: '/payments-operations/audit',
    labelKey: 'payMp002.nav.audit',
    permission: 'audit.read',
    descriptionKey: 'payMp002.nav.auditDescription',
  },
];

export type PayMp002AdminScope =
  | { kind: 'platform'; ref: 'platform:eslatin'; tenantId: null }
  | { kind: 'tenant'; ref: string; tenantId: string }
  | { kind: 'unavailable'; ref: null; tenantId: null };

/** Resolve display/cache scope without fabricating a tenant for platform scope. */
export function resolvePayMp002Scope(
  user: Pick<AdminUser, 'is_super_admin'> | null | undefined,
  currentTenant: Pick<Tenant, 'id'> | null | undefined,
): PayMp002AdminScope {
  if (!user) return { kind: 'unavailable', ref: null, tenantId: null };
  if (currentTenant?.id) {
    return { kind: 'tenant', ref: `tenant:${currentTenant.id}`, tenantId: currentTenant.id };
  }
  if (user?.is_super_admin) {
    return { kind: 'platform', ref: 'platform:eslatin', tenantId: null };
  }
  return { kind: 'unavailable', ref: null, tenantId: null };
}

export function payMp002CacheKey(
  resource: PayMp002Resource,
  scope: PayMp002AdminScope,
  cursor: string | null = null,
): readonly [string, string, string | null] {
  return ['pay-mp-002', `${resource}:${scope.ref ?? 'unavailable'}`, cursor];
}

export function isPayMp002Permission(value: string): value is PayMp002Permission {
  return (PAY_MP_002_PERMISSIONS as readonly string[]).includes(value);
}

export function canUsePayMp002Permission(
  permissions: readonly string[] | null | undefined,
  required: PayMp002Permission,
): boolean {
  if (!isPayMp002Permission(required)) return false;
  return permissions?.includes(required) === true
    || permissions?.includes('*') === true
    || permissions?.includes('tenant.*') === true;
}

export function hasAllowedAction(
  projection: { allowed_actions?: readonly string[] } | null | undefined,
  action: string,
): boolean {
  return projection?.allowed_actions?.includes(action) === true;
}

export function payMp002ScopeLabel(scope: PayMp002AdminScope): string {
  if (scope.kind === 'platform') return 'platform:eslatin';
  if (scope.kind === 'tenant') return scope.ref;
  return 'scope unavailable';
}

export function canonicalErrorMessageKey(error: CanonicalError): string {
  const keys: Record<string, string> = {
    CONTRACT_VERSION_UNSUPPORTED: 'payMp002.contractVersionUnsupported',
    PAGINATION_MODE_INVALID: 'payMp002.paginationModeInvalid',
    CURSOR_INVALID: 'payMp002.cursorInvalid',
    PERMISSION_DENIED: 'payMp002.permissionDenied',
    RESOURCE_NOT_FOUND: 'payMp002.resourceNotFound',
    RECOVERY_UNKNOWN: 'payMp002.recoveryUnknown',
    FINANCIAL_ELIGIBILITY_BLOCKED: 'payMp002.financialEligibilityBlocked',
    FINANCIAL_RECHECK_REQUIRED: 'payMp002.financialRecheckRequired',
    PROVIDER_UNAVAILABLE: 'payMp002.providerUnavailable',
    EXPORT_NOT_READY: 'payMp002.exportNotReady',
    EXPORT_FAILED: 'payMp002.exportFailed',
    EXPORT_CONSUMED: 'payMp002.exportConsumed',
    EXPORT_EXPIRED: 'payMp002.exportExpired',
    RESOURCE_VERSION_CONFLICT: 'payMp002.staleVersion',
  };
  return keys[error.code] ?? 'payMp002.error';
}

export function projectionFrame(
  projection: unknown,
  scope: PayMp002AdminScope,
) {
  const value = projection && typeof projection === 'object'
    ? projection as {
      allowed_actions?: readonly string[];
      version?: number;
      created_at?: string;
      updated_at?: string;
      timeline?: readonly unknown[];
    }
    : {};
  return {
    scope,
    version: value.version ?? 0,
    created_at: value.created_at ?? null,
    updated_at: value.updated_at ?? null,
    allowed_actions: value.allowed_actions ?? [],
    timeline_count: value.timeline?.length ?? 0,
  } as const;
}
