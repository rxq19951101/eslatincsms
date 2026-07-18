import type { z } from 'zod';

import type { TenantProvisionRequest, TenantProvisionResponse, TenantProvisionResult } from '@/types';
import { tenantProvisionSchema } from '@/lib/validation';

type ValidTenantProvisionForm = z.infer<typeof tenantProvisionSchema>;

export function tenantProvisionPayload(data: ValidTenantProvisionForm): TenantProvisionRequest {
  return {
    tenant: {
      name: data.name,
      domain: data.domain || null,
      subscription_plan: data.subscription_plan,
      max_charge_points: data.max_charge_points,
      max_users: data.max_users,
      settings: {},
    },
    admin: {
      username: data.admin_username,
      email: data.admin_email,
      password: data.admin_password,
      full_name: data.admin_full_name || null,
    },
  };
}

export function tenantProvisionResult(
  response: TenantProvisionResponse,
  temporaryPassword: string
): TenantProvisionResult {
  return { ...response, temporary_password: temporaryPassword };
}
