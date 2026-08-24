import { z } from 'zod';
import { ApiRequestError } from '@/lib/api';

export type ValidationMessageKey =
  | 'validation.required'
  | 'validation.siteNameLength'
  | 'validation.addressLength'
  | 'validation.latitude'
  | 'validation.longitude'
  | 'validation.zeroCoordinates'
  | 'validation.operatingHoursLength'
  | 'validation.ocppIdentity'
  | 'validation.displayCode'
  | 'validation.textTooLong'
  | 'validation.connectorCount'
  | 'validation.positiveAmount'
  | 'validation.moneyPrecision'
  | 'validation.reasonRequired'
  | 'validation.reasonLength'
  | 'validation.tenantNameLength'
  | 'validation.domain'
  | 'validation.plan'
  | 'validation.limit'
  | 'validation.username'
  | 'validation.email'
  | 'validation.passwordLength'
  | 'validation.passwordMismatch'
  | 'validation.price'
  | 'validation.configKey'
  | 'validation.configValue';

const trimmedString = (minimum: number, maximum: number, message: ValidationMessageKey) =>
  z.string().trim().min(minimum, message).max(maximum, message);

const optionalTrimmedString = (maximum: number) =>
  z.string().trim().max(maximum, 'validation.textTooLong').optional().or(z.literal(''));

const requiredCoordinate = (
  minimum: number,
  maximum: number,
  message: 'validation.latitude' | 'validation.longitude'
) => z.preprocess(
  (value) => typeof value === 'string' && value.trim() === '' ? undefined : value,
  z.coerce.number({ error: message }).min(minimum, message).max(maximum, message)
);

export const siteSchema = z
  .object({
    name: trimmedString(2, 120, 'validation.siteNameLength'),
    address: trimmedString(5, 300, 'validation.addressLength'),
    latitude: requiredCoordinate(-90, 90, 'validation.latitude'),
    longitude: requiredCoordinate(-180, 180, 'validation.longitude'),
    operating_hours: z.string().trim().max(500, 'validation.operatingHoursLength').optional().or(z.literal('')),
  })
  .superRefine(({ latitude, longitude }, context) => {
    if (latitude === 0 && longitude === 0) {
      for (const path of ['latitude', 'longitude']) {
        context.addIssue({ code: 'custom', path: [path], message: 'validation.zeroCoordinates' });
      }
    }
  });

export const chargePointSchema = z.object({
  id: z.string().trim().regex(/^[A-Za-z0-9._:-]{1,64}$/, 'validation.ocppIdentity'),
  display_code: z.string().trim().regex(/^[A-Z][A-Z0-9-]{0,15}$/, 'validation.displayCode'),
  display_name: optionalTrimmedString(80),
  location_hint: optionalTrimmedString(160),
  vendor: optionalTrimmedString(120),
  model: optionalTrimmedString(120),
  connector_count: z.coerce.number().int('validation.connectorCount').min(1, 'validation.connectorCount').max(16, 'validation.connectorCount'),
  connector_type: z.enum(['Type2', 'CCS1', 'CCS2', 'CHAdeMO', 'NACS', 'GB_T_AC', 'GB_T_DC']),
  evses: z.array(z.object({
    evse_id: z.coerce.number().int().min(1).max(16),
    physical_reference: z.string().trim().regex(/^[A-Za-z0-9._:-]{1,64}$/, 'validation.ocppIdentity'),
    connector_type: z.enum(['Type2', 'CCS1', 'CCS2', 'CHAdeMO', 'NACS', 'GB_T_AC', 'GB_T_DC']),
    max_power_kw: z.coerce.number().positive().max(1000),
  })).min(1).max(16).optional(),
});

const optionalDomain = z
  .string()
  .trim()
  .max(200, 'validation.domain')
  .refine((value) => !value || (value.length >= 3 && /^[A-Za-z0-9.-]+$/.test(value)), 'validation.domain');

export const tenantProvisionSchema = z.object({
  name: trimmedString(2, 200, 'validation.tenantNameLength'),
  domain: optionalDomain,
  subscription_plan: z.enum(['free', 'pro', 'enterprise'], { message: 'validation.plan' }),
  max_charge_points: z.coerce.number().int('validation.limit').min(1, 'validation.limit').max(100_000, 'validation.limit'),
  max_users: z.coerce.number().int('validation.limit').min(1, 'validation.limit').max(10_000_000, 'validation.limit'),
  admin_username: z.string().trim().regex(/^[A-Za-z0-9._-]{3,100}$/, 'validation.username'),
  admin_email: z.string().trim().email('validation.email').max(254, 'validation.email'),
  admin_full_name: optionalTrimmedString(200),
  admin_password: z.string().min(8, 'validation.passwordLength').max(128, 'validation.passwordLength'),
});

const decimalAmount = z
  .string()
  .trim()
  .regex(/^-?(?:\d+)(?:\.\d{1,2})?$/, 'validation.moneyPrecision')
  .refine((value) => {
    const [integerPart, fractionalPart = ''] = value.replace(/^-/, '').split('.');
    const integerDigits = integerPart.replace(/^0+/, '').length;
    return integerDigits + fractionalPart.length <= 10;
  }, 'validation.moneyPrecision')
  .refine((value) => Number(value) !== 0, 'validation.positiveAmount');

export const walletAdjustmentSchema = z.object({
  amount: decimalAmount,
  description: trimmedString(1, 500, 'validation.reasonLength'),
});

export const priceSchema = z.object({
  price: z.coerce.number().positive('validation.price').max(1_000_000, 'validation.price'),
});

export const profileSchema = z.object({
  full_name: optionalTrimmedString(120),
  email: z.string().trim().email('validation.email').max(254, 'validation.email'),
});

export const passwordSchema = z
  .object({
    old_password: trimmedString(1, 128, 'validation.required'),
    new_password: z.string().min(8, 'validation.passwordLength').max(128, 'validation.passwordLength'),
    confirm_password: z.string(),
  })
  .refine(({ new_password, confirm_password }) => new_password === confirm_password, {
    path: ['confirm_password'],
    message: 'validation.passwordMismatch',
  });

export const tenantSettingsSchema = z.object({
  name: trimmedString(2, 120, 'validation.tenantNameLength'),
  domain: optionalDomain,
});

export const configSchema = z.object({
  config_key: trimmedString(1, 200, 'validation.configKey'),
  config_value: z.string().max(5000, 'validation.configValue'),
});

export type FieldErrors = Record<string, ValidationMessageKey>;

type ApiFieldMapping = Record<string, readonly [formField: string, message: ValidationMessageKey]>;

export function fieldErrors(error: z.ZodError): FieldErrors {
  return error.issues.reduce<FieldErrors>((result, issue) => {
    const field = String(issue.path[0] ?? 'form');
    if (!result[field]) result[field] = issue.message as ValidationMessageKey;
    return result;
  }, {});
}

export function apiFieldErrors(error: unknown, mapping: ApiFieldMapping): FieldErrors {
  if (!(error instanceof ApiRequestError)) return {};
  return Object.keys(error.fieldErrors).reduce<FieldErrors>((result, path) => {
    const target = mapping[path] ?? mapping[path.split('.').at(-1) ?? path];
    if (target && !result[target[0]]) result[target[0]] = target[1];
    return result;
  }, {});
}

export const SITE_API_FIELD_MAPPING = {
  name: ['name', 'validation.siteNameLength'],
  address: ['address', 'validation.addressLength'],
  latitude: ['latitude', 'validation.latitude'],
  longitude: ['longitude', 'validation.longitude'],
  operating_hours: ['operating_hours', 'validation.operatingHoursLength'],
} as const satisfies ApiFieldMapping;

export const TENANT_PROVISION_API_FIELD_MAPPING = {
  'tenant.name': ['name', 'validation.tenantNameLength'],
  'tenant.domain': ['domain', 'validation.domain'],
  'tenant.subscription_plan': ['subscription_plan', 'validation.plan'],
  'tenant.max_charge_points': ['max_charge_points', 'validation.limit'],
  'tenant.max_users': ['max_users', 'validation.limit'],
  'admin.username': ['admin_username', 'validation.username'],
  'admin.email': ['admin_email', 'validation.email'],
  'admin.full_name': ['admin_full_name', 'validation.textTooLong'],
  'admin.password': ['admin_password', 'validation.passwordLength'],
} as const satisfies ApiFieldMapping;

export const WALLET_API_FIELD_MAPPING = {
  amount: ['amount', 'validation.moneyPrecision'],
  description: ['description', 'validation.reasonLength'],
} as const satisfies ApiFieldMapping;

export function makeIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `adm-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function apiErrorMessageKey(error: unknown, fallback: string): string {
  const status = typeof error === 'object' && error && 'status' in error
    ? Number((error as { status?: number }).status)
    : undefined;
  if (status === 401) return 'api.unauthorized';
  if (status === 403) return 'api.forbidden';
  if (status === 404) return 'api.notFound';
  if (status === 409) return 'api.conflict';
  if (status === 422) return 'api.validation';
  if (status && status >= 500) return 'api.server';
  return fallback;
}
