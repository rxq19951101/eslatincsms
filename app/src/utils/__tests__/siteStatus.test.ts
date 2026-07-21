import type { SiteStatusCounts } from '../../api/sites';
import {
  getSiteStatusBreakdown,
  getSiteStatusColor,
  getSiteAvailability,
  hasChargingWithoutAvailability,
} from '../siteStatus';

const mixedCounts: SiteStatusCounts = {
  available: 0,
  charging: 1,
  offline: 1,
  faulted: 0,
  occupied: 0,
  unavailable: 0,
  unknown: 0,
};

describe('site status presentation', () => {
  it('keeps meaningful mixed states in a stable display order', () => {
    expect(getSiteStatusBreakdown(mixedCounts)).toEqual([
      { status: 'charging', count: 1 },
      { status: 'offline', count: 1 },
    ]);
  });

  it('uses the no-free state only when charging exists without availability', () => {
    expect(hasChargingWithoutAvailability(0, mixedCounts)).toBe(true);
    expect(hasChargingWithoutAvailability(1, mixedCounts)).toBe(false);
    expect(hasChargingWithoutAvailability(0, undefined)).toBe(false);
  });

  it('remains backward-compatible when status counts are absent', () => {
    expect(getSiteStatusBreakdown(undefined)).toEqual([]);
  });

  it('derives station availability without exposing device states', () => {
    expect(getSiteAvailability(1, mixedCounts, 'Charging')).toBe('availableToCharge');
    expect(getSiteAvailability(0, mixedCounts, 'Offline')).toBe('siteNoConnectorsFree');
    expect(getSiteAvailability(0, { ...mixedCounts, charging: 0, occupied: 1 }, 'Offline'))
      .toBe('siteNoConnectorsFree');
    expect(getSiteAvailability(0, { ...mixedCounts, charging: 0 }, 'Charging'))
      .toBe('temporarilyUnavailable');
  });

  it.each([
    ['Charging', 'siteNoConnectorsFree'],
    ['Offline', 'temporarilyUnavailable'],
    ['Unavailable', 'temporarilyUnavailable'],
    ['Faulted', 'temporarilyUnavailable'],
  ])('falls back from legacy %s to %s when counts are absent', (legacyStatus, expected) => {
    expect(getSiteAvailability(0, undefined, legacyStatus)).toBe(expected);
  });

  it('uses distinct readable colors for charging and offline states', () => {
    expect(getSiteStatusColor('charging')).not.toBe(getSiteStatusColor('offline'));
    expect(getSiteStatusColor('offline')).toBe('#5B7083');
  });
});
