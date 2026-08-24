import { describe, expect, it } from 'vitest';

import { isOperationalSite, operationalChargePointCount } from '../assetLifecycle';
import type { SiteListItem } from '@/types';

const site = (overrides: Partial<SiteListItem> = {}): SiteListItem => ({
  id: 'site-1',
  site_code: 'SITE-1',
  name: 'Operational site',
  address: 'Bogota',
  latitude: 4.6,
  longitude: -74.1,
  is_active: true,
  charge_points_count: 4,
  online_charge_points_count: 2,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  ...overrides,
});

describe('asset lifecycle presentation helpers', () => {
  it('keeps only operational sites in ordinary views', () => {
    expect(isOperationalSite(site())).toBe(true);
    expect(isOperationalSite(site({ is_active: false }))).toBe(false);
    expect(isOperationalSite(site({ lifecycle_status: 'archived' }))).toBe(false);
  });

  it('prefers the explicit active charger count', () => {
    expect(operationalChargePointCount(site({ active_charge_points_count: 3 }))).toBe(3);
    expect(operationalChargePointCount(site())).toBe(4);
  });
});
