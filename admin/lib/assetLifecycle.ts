import type { SiteListItem } from '@/types';

/** Defensive client-side guard for ordinary operational views. */
export const isOperationalSite = (site: SiteListItem): boolean =>
  site.is_active !== false && site.lifecycle_status !== 'archived';

/** Prefer the explicit lifecycle count when the API provides it. */
export const operationalChargePointCount = (site: SiteListItem): number =>
  site.active_charge_points_count ?? site.charge_points_count;
