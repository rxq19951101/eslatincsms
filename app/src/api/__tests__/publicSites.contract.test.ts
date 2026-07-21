import apiClient from '../client';
import { getChargers, getNearbyChargers } from '../chargers';

jest.mock('../client', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('public App station contract', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedClient.get.mockResolvedValue({ data: [] });
  });

  it('never sends a tenant filter for the public station list', async () => {
    await getChargers({ filter_type: 'configured' });
    await getNearbyChargers(4.711, -74.072, 5000);

    for (const call of mockedClient.get.mock.calls) {
      const params = call[1]?.params || {};
      expect(params).not.toHaveProperty('tenant_id');
      expect(params).not.toHaveProperty('tenantId');
    }
  });
});
