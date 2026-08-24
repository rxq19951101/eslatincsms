import apiClient from '../client';
import { getFavoriteSites, removeFavoriteSite, saveFavoriteSite } from '../favorites';

jest.mock('../client', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const mockedClient = apiClient as jest.Mocked<typeof apiClient>;

describe('App favorite site contract', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lists the current user saved sites', async () => {
    mockedClient.get.mockResolvedValueOnce({ data: [{
      id: '11111111-1111-4111-8111-111111111111',
      name: 'Bogotá Centro',
      is_favorite: true,
    }] });

    const sites = await getFavoriteSites();

    expect(mockedClient.get).toHaveBeenCalledWith('/api/v1/app/favorites');
    expect(sites[0]).toMatchObject({ is_favorite: true });
  });

  it('uses idempotent PUT and DELETE routes for the station', async () => {
    const siteId = '11111111-1111-4111-8111-111111111111';
    mockedClient.put.mockResolvedValueOnce({ data: { site_id: siteId, is_favorite: true } });
    mockedClient.delete.mockResolvedValueOnce({ data: { site_id: siteId, is_favorite: false } });

    await saveFavoriteSite(siteId);
    await removeFavoriteSite(siteId);

    expect(mockedClient.put).toHaveBeenCalledWith(`/api/v1/app/favorites/${siteId}`);
    expect(mockedClient.delete).toHaveBeenCalledWith(`/api/v1/app/favorites/${siteId}`);
  });
});
