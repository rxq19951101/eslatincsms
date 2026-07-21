import { describe, expect, it } from 'vitest';

import { translateMessage } from '@/lib/i18n';
import { ApiRequestError } from '@/lib/api';
import {
  apiFieldErrors,
  chargePointSchema,
  fieldErrors,
  siteSchema,
  SITE_API_FIELD_MAPPING,
  TENANT_PROVISION_API_FIELD_MAPPING,
  tenantProvisionSchema,
  WALLET_API_FIELD_MAPPING,
  walletAdjustmentSchema,
} from '@/lib/validation';

describe('Admin write validation', () => {
  it.each([
    [{ name: '', address: 'Bogotá DC', latitude: '4.6', longitude: '-74.1' }, 'name'],
    [{ name: 'Central', address: '   ', latitude: '4.6', longitude: '-74.1' }, 'address'],
    [{ name: 'Central', address: 'Bogotá DC', latitude: '91', longitude: '-74.1' }, 'latitude'],
    [{ name: 'Central', address: 'Bogotá DC', latitude: '0', longitude: '0' }, 'latitude'],
  ])('rejects invalid site input %#', (input, expectedField) => {
    const result = siteSchema.safeParse(input);
    expect(result.success).toBe(false);
    if (!result.success) expect(fieldErrors(result.error)).toHaveProperty(expectedField);
  });

  it.each([
    { latitude: '', longitude: '-74.1', field: 'latitude' },
    { latitude: '   ', longitude: '-74.1', field: 'latitude' },
    { latitude: '4.6', longitude: '', field: 'longitude' },
    { latitude: '4.6', longitude: '   ', field: 'longitude' },
  ])('requires explicit coordinates: $field', ({ latitude, longitude, field }) => {
    const result = siteSchema.safeParse({
      name: 'Central',
      address: 'Bogotá DC',
      latitude,
      longitude,
    });
    expect(result.success).toBe(false);
    if (!result.success) expect(fieldErrors(result.error)).toHaveProperty(field);
  });

  it('trims a valid site and keeps coordinates numeric', () => {
    const result = siteSchema.parse({
      name: '  Zona Norte  ',
      address: '  Calle 100 # 10-20  ',
      latitude: '4.684',
      longitude: '-74.047',
      operating_hours: '  24/7  ',
    });
    expect(result).toEqual({
      name: 'Zona Norte',
      address: 'Calle 100 # 10-20',
      latitude: 4.684,
      longitude: -74.047,
      operating_hours: '24/7',
    });
  });

  it.each(['CP-01', 'CO.BOGOTA:CP_01', 'vendor.device'])('accepts OCPP identity %s', (id) => {
    expect(chargePointSchema.safeParse({ id, display_code: 'A01', connector_count: 1, connector_type: 'Type2' }).success).toBe(true);
  });

  it.each(['', '空格', 'CP/01', 'A'.repeat(65)])('rejects OCPP identity %s', (id) => {
    expect(chargePointSchema.safeParse({ id, display_code: 'A01', connector_count: 1, connector_type: 'Type2' }).success).toBe(false);
  });

  it('validates and trims public charger and connector labels', () => {
    const result = chargePointSchema.parse({
      id: 'CO.BOGOTA:CP_01',
      display_code: '  A01  ',
      display_name: '  North entrance  ',
      location_hint: '  P2 / bay 42  ',
      connector_count: 1,
      connector_type: 'Type2',
      evses: [{ evse_id: 1, physical_reference: ' A01-1 ', connector_type: 'Type2', max_power_kw: '7' }],
    });

    expect(result).toMatchObject({
      display_code: 'A01',
      display_name: 'North entrance',
      location_hint: 'P2 / bay 42',
      evses: [{ physical_reference: 'A01-1', max_power_kw: 7 }],
    });
    expect(chargePointSchema.safeParse({
      id: 'CP-01', display_code: 'A/01', connector_count: 1, connector_type: 'Type2',
    }).success).toBe(false);
  });

  it('matches public-label limits and supported connector types', () => {
    const base = { id: 'CP-01', display_code: 'A01', connector_count: 1, connector_type: 'Type2' };

    expect(chargePointSchema.safeParse({ ...base, display_code: 'A'.repeat(16) }).success).toBe(true);
    expect(chargePointSchema.safeParse({ ...base, display_code: 'A-01' }).success).toBe(true);
    expect(chargePointSchema.safeParse({ ...base, display_code: 'a01' }).success).toBe(false);
    expect(chargePointSchema.safeParse({ ...base, display_code: '1A01' }).success).toBe(false);
    expect(chargePointSchema.safeParse({ ...base, display_code: 'A'.repeat(17) }).success).toBe(false);
    expect(chargePointSchema.safeParse({ ...base, display_name: 'N'.repeat(80) }).success).toBe(true);
    expect(chargePointSchema.safeParse({ ...base, display_name: 'N'.repeat(81) }).success).toBe(false);
    expect(chargePointSchema.safeParse({ ...base, location_hint: 'L'.repeat(160) }).success).toBe(true);
    expect(chargePointSchema.safeParse({ ...base, location_hint: 'L'.repeat(161) }).success).toBe(false);

    for (const connector_type of ['Type2', 'CCS1', 'CCS2', 'CHAdeMO', 'NACS', 'GB_T_AC', 'GB_T_DC']) {
      expect(chargePointSchema.safeParse({
        ...base,
        evses: [{ evse_id: 1, physical_reference: 'A01-1', connector_type, max_power_kw: 7 }],
      }).success).toBe(true);
    }
    expect(chargePointSchema.safeParse({
      ...base,
      evses: [{ evse_id: 1, physical_reference: 'A01-1', connector_type: 'custom', max_power_kw: 7 }],
    }).success).toBe(false);
  });

  it('requires an atomic tenant provision payload with a valid first admin', () => {
    const result = tenantProvisionSchema.safeParse({
      name: 'EsLatin Colombia',
      domain: 'co.eslatin.example',
      subscription_plan: 'pro',
      max_charge_points: 50,
      max_users: 500,
      admin_username: 'tenant_admin',
      admin_email: 'admin@example.com',
      admin_full_name: 'Admin',
      admin_password: 'strong-pass-123',
    });
    expect(result.success).toBe(true);
  });

  it('matches the backend tenant provision upper boundaries', () => {
    const valid = {
      name: 'N'.repeat(200),
      domain: 'a.b',
      subscription_plan: 'enterprise',
      max_charge_points: 100_000,
      max_users: 10_000_000,
      admin_username: 'u'.repeat(100),
      admin_email: 'admin@example.com',
      admin_full_name: 'A'.repeat(200),
      admin_password: 'p'.repeat(128),
    } as const;
    expect(tenantProvisionSchema.safeParse(valid).success).toBe(true);
    expect(tenantProvisionSchema.safeParse({ ...valid, name: 'N'.repeat(201) }).success).toBe(false);
    expect(tenantProvisionSchema.safeParse({ ...valid, max_users: 10_000_001 }).success).toBe(false);
    expect(tenantProvisionSchema.safeParse({ ...valid, admin_username: 'u'.repeat(101) }).success).toBe(false);
    expect(tenantProvisionSchema.safeParse({ ...valid, admin_full_name: 'A'.repeat(201) }).success).toBe(false);
  });

  it.each(['0', '10.001', 'abc'])('rejects invalid wallet amount %s', (amount) => {
    expect(walletAdjustmentSchema.safeParse({ amount, description: 'Manual correction' }).success).toBe(false);
  });

  it('requires a wallet reason', () => {
    const result = walletAdjustmentSchema.safeParse({ amount: '-10.25', description: ' ' });
    expect(result.success).toBe(false);
    if (!result.success) expect(fieldErrors(result.error).description).toBe('validation.reasonLength');
  });

  it('matches wallet Decimal and description boundaries', () => {
    expect(walletAdjustmentSchema.safeParse({ amount: '99999999.99', description: 'x' }).success).toBe(true);
    expect(walletAdjustmentSchema.safeParse({ amount: '999999999.99', description: 'x' }).success).toBe(false);
    expect(walletAdjustmentSchema.safeParse({ amount: '-0.01', description: 'x'.repeat(500) }).success).toBe(true);
    expect(walletAdjustmentSchema.safeParse({ amount: '-0.01', description: 'x'.repeat(501) }).success).toBe(false);
  });

  it('maps backend field paths to local translated field errors', () => {
    const siteError = new ApiRequestError('invalid', 422, { latitude: 'Input required' });
    expect(apiFieldErrors(siteError, SITE_API_FIELD_MAPPING)).toEqual({
      latitude: 'validation.latitude',
    });

    const provisionError = new ApiRequestError('invalid', 422, {
      'tenant.name': 'String too long',
      'admin.username': 'String pattern mismatch',
    });
    expect(apiFieldErrors(provisionError, TENANT_PROVISION_API_FIELD_MAPPING)).toEqual({
      name: 'validation.tenantNameLength',
      admin_username: 'validation.username',
    });

    const walletError = new ApiRequestError('invalid', 422, { description: 'String too long' });
    const messageKey = apiFieldErrors(walletError, WALLET_API_FIELD_MAPPING).description;
    expect([
      translateMessage('zh-CN', messageKey),
      translateMessage('en', messageKey),
      translateMessage('es', messageKey),
    ]).toEqual([
      '调整原因需为 1–500 个字符',
      'Reason must be 1–500 characters',
      'El motivo debe tener entre 1 y 500 caracteres',
    ]);
  });

  it.each([
    ['zh-CN', '站点名称需为 2–120 个字符'],
    ['en', 'Site name must be 2–120 characters'],
    ['es', 'El nombre del sitio debe tener entre 2 y 120 caracteres'],
  ] as const)('provides %s validation messages', (locale, expected) => {
    expect(translateMessage(locale, 'validation.siteNameLength')).toBe(expected);
  });

  it.each([
    ['zh-CN', [
      '租户名称需为 2–200 个字符',
      '请输入有效域名（最多 200 个字符）',
      '用户名需为 3–100 位 ASCII 字母、数字、点、下划线或连字符',
      '密码需为 8–128 个字符',
    ]],
    ['en', [
      'Tenant name must be 2–200 characters',
      'Enter a valid domain (up to 200 characters)',
      'Username must be 3–100 ASCII letters, numbers, dots, underscores, or hyphens',
      'Password must be 8–128 characters',
    ]],
    ['es', [
      'El nombre del inquilino debe tener entre 2 y 200 caracteres',
      'Ingresa un dominio válido (máximo 200 caracteres)',
      'El usuario debe tener 3–100 letras ASCII, números, puntos, guiones bajos o guiones',
      'La contraseña debe tener entre 8 y 128 caracteres',
    ]],
  ] as const)('keeps %s provision boundary messages aligned', (locale, expected) => {
    expect([
      translateMessage(locale, 'validation.tenantNameLength'),
      translateMessage(locale, 'validation.domain'),
      translateMessage(locale, 'validation.username'),
      translateMessage(locale, 'validation.passwordLength'),
    ]).toEqual(expected);
  });
});
