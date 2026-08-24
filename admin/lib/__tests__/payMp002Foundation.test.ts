import { describe, expect, it } from 'vitest';
import {
  PAY_MP_002_NAVIGATION,
  PAY_MP_002_PERMISSIONS,
  canUsePayMp002Permission,
  canonicalErrorMessageKey,
  hasAllowedAction,
  payMp002CacheKey,
  resolvePayMp002Scope,
} from '../payMp002Foundation';

describe('PAY-MP-002 FE-206 Admin foundation', () => {
  it('keeps the frozen permission vocabulary and navigation provider-neutral', () => {
    expect(PAY_MP_002_PERMISSIONS).toEqual([
      'payment.read', 'refund.request', 'refund.approve', 'chargeback.read',
      'reconciliation.read', 'reconciliation.resolve', 'reconciliation.exception.request',
      'reconciliation.exception.approve', 'support.manage', 'rail.read', 'rail.close',
      'rail.reopen.request', 'rail.reopen.approve', 'audit.read',
    ]);
    expect(PAY_MP_002_NAVIGATION.map((item) => item.resource)).toEqual([
      'refunds', 'chargebacks', 'reconciliation', 'support', 'rails', 'audit',
    ]);
    expect(PAY_MP_002_NAVIGATION.every((item) => !item.href.includes('provider'))).toBe(true);
  });

  it('uses exact server permissions and resource allowed_actions', () => {
    expect(canUsePayMp002Permission(['refund.approve'], 'refund.approve')).toBe(true);
    expect(canUsePayMp002Permission(['refund.approve'], 'refund.request')).toBe(false);
    expect(canUsePayMp002Permission(['is_super_admin'], 'audit.read')).toBe(false);
    expect(hasAllowedAction({ allowed_actions: ['view', 'refresh'] }, 'approve')).toBe(false);
    expect(hasAllowedAction({ allowed_actions: ['view', 'refresh'] }, 'refresh')).toBe(true);
  });

  it('does not fabricate a tenant for platform scope and isolates cache keys', () => {
    const platform = resolvePayMp002Scope({ is_super_admin: true }, null);
    const tenant = resolvePayMp002Scope({ is_super_admin: false }, { id: 'tenant-7' });
    const unavailable = resolvePayMp002Scope({ is_super_admin: false }, null);
    expect(platform).toEqual({ kind: 'platform', ref: 'platform:eslatin', tenantId: null });
    expect(tenant).toEqual({ kind: 'tenant', ref: 'tenant:tenant-7', tenantId: 'tenant-7' });
    expect(unavailable.kind).toBe('unavailable');
    expect(payMp002CacheKey('refunds', platform)).not.toEqual(payMp002CacheKey('refunds', tenant));
    expect(payMp002CacheKey('refunds', tenant)).not.toEqual(payMp002CacheKey('support', tenant));
  });

  it('maps canonical errors to safe localized keys', () => {
    expect(canonicalErrorMessageKey({
      code: 'PERMISSION_DENIED', message: 'unsafe provider text', reference: 'ref-1', retryable: false,
      retry_after_seconds: null,
    })).toBe('payMp002.permissionDenied');
    expect(canonicalErrorMessageKey({
      code: 'UNEXPECTED_CODE', message: 'unsafe', reference: null, retryable: false,
      retry_after_seconds: null,
    })).toBe('payMp002.error');
    expect(canonicalErrorMessageKey({
      code: 'RESOURCE_VERSION_CONFLICT', message: 'unsafe', reference: null, retryable: false,
      retry_after_seconds: null, current_version: 3,
    })).toBe('payMp002.staleVersion');
  });
});
