import apiClient from '../client';
import { getSiteById, getSites } from '../sites';

jest.mock('../client', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('App public site contract', () => {
  beforeEach(() => jest.clearAllMocks());

  it('loads one aggregated record per site with location filters', async () => {
    mockedClient.get.mockResolvedValueOnce({
      data: [{
        id: '11111111-1111-4111-8111-111111111111',
        name: 'Bogotá Centro',
        address: 'Calle 100 # 10-20',
        latitude: 4.61,
        longitude: -74.08,
        status: 'Available',
        charger_count: 2,
        available_connectors: 3,
        total_connectors: 4,
        status_counts: {
          available: 3, charging: 1, offline: 0, faulted: 0,
          occupied: 0, unavailable: 0, unknown: 0,
        },
        connector_types: ['CCS2', 'Type2'],
        charging_options: [
          {
            standard: 'CCS_2', current_type: 'DC', max_power_kw: 120, available: 2, total: 3,
            status_counts: {
              available: 2, charging: 1, offline: 0, faulted: 0,
              occupied: 0, unavailable: 0, unknown: 0,
            },
          },
          { standard: 'TYPE_2', current_type: 'AC', max_power_kw: 7, available: 1, total: 1 },
        ],
        max_power_kw: 120,
        price_per_kwh: 2700,
        has_pricing: true,
      }],
    });

    const sites = await getSites({ latitude: 4.61, longitude: -74.08, radius: 5000 });

    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/sites', {
      params: { latitude: 4.61, longitude: -74.08, radius: 5000 },
    });
    expect(sites).toHaveLength(1);
    expect(sites[0]).toMatchObject({ charger_count: 2, total_connectors: 4 });
    expect(sites[0].status_counts).toMatchObject({ available: 3, charging: 1 });
    expect(sites[0].charging_options[0]).toMatchObject({
      standard: 'CCS_2', max_power_kw: 120,
      status_counts: { available: 2, charging: 1 },
    });
  });

  it('loads the site hierarchy without exposing OCPP identity as a public name', async () => {
    const siteId = '11111111-1111-4111-8111-111111111111';
    mockedClient.get.mockResolvedValueOnce({
      data: {
        id: siteId,
        name: 'Bogotá Centro',
        address: 'Calle 100 # 10-20',
        latitude: 4.61,
        longitude: -74.08,
        status: 'Available',
        charger_count: 1,
        available_connectors: 1,
        total_connectors: 1,
        connector_types: ['Type2'],
        charging_options: [
          { standard: 'TYPE_2', current_type: 'AC', max_power_kw: 7, available: 1, total: 1 },
        ],
        max_power_kw: 7,
        price_per_kwh: 2700,
        has_pricing: true,
        charge_points: [{
          id: '22222222-2222-4222-8222-222222222222',
          display_code: 'A01',
          display_name: 'North entrance',
          location_hint: 'P2 / bay 42',
          status: 'Available',
          vendor: 'EsLatin',
          model: 'AC7',
          connectors: [{
            id: '33333333-3333-4333-8333-333333333333',
            connector_id: 1,
            physical_reference: 'A01-1',
            status: 'Available',
            connector_type: 'Type2',
            power_kw: 7,
          }],
        }],
      },
    });

    const site = await getSiteById(siteId);

    expect(mockedClient.get).toHaveBeenCalledWith(`/api/v1/app/sites/${siteId}`);
    expect(site.charge_points[0]).toMatchObject({
      display_code: 'A01', display_name: 'North entrance', location_hint: 'P2 / bay 42',
    });
    expect(site.charge_points[0].connectors[0]).toMatchObject({
      physical_reference: 'A01-1', connector_type: 'Type2', power_kw: 7,
    });
    expect(site.charge_points[0]).not.toHaveProperty('ocpp_identity');
  });
});
