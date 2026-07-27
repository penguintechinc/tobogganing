import apiClient from './client';
import { listClusters, listClients, getStatus } from './sase';

jest.mock('./client');
const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

describe('SASE API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listClusters', () => {
    it('fetches clusters from the API', async () => {
      const mockClusters = [
        {
          id: '1',
          name: 'cluster-1',
          region: 'us-east-1',
          datacenter: 'dc-1',
          status: 'active',
          client_count: 5,
        },
      ];
      const mockResponse = {
        data: {
          clusters: mockClusters,
          meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
        },
      };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await listClusters();

      expect(mockApiClient.get).toHaveBeenCalledWith('/sdwan/clusters');
      expect(result).toEqual(mockClusters);
    });

    it('returns empty array on empty response', async () => {
      const mockResponse = {
        data: {
          clusters: [],
          meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
        },
      };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await listClusters();

      expect(result).toEqual([]);
    });
  });

  describe('listClients', () => {
    it('fetches clients from the API', async () => {
      const mockClients = [
        {
          id: '1',
          name: 'client-1',
          type: 'docker',
          cluster_id: 'cluster-1',
          status: 'active',
          last_seen: '2026-07-15T10:00:00Z',
        },
      ];
      const mockResponse = {
        data: {
          clients: mockClients,
          meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
        },
      };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await listClients();

      expect(mockApiClient.get).toHaveBeenCalledWith('/sdwan/clients');
      expect(result).toEqual(mockClients);
    });

    it('returns empty array on empty response', async () => {
      const mockResponse = {
        data: {
          clients: [],
          meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
        },
      };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await listClients();

      expect(result).toEqual([]);
    });
  });

  describe('getStatus', () => {
    it('fetches status from the API', async () => {
      const mockStatus = {
        service: 'SASE Orchestrator API',
        status: 'healthy',
        clusters: { total: 5, active: 4 },
        clients: { total: 20, active: 18 },
        meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
      };
      const mockResponse = { data: mockStatus };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await getStatus();

      expect(mockApiClient.get).toHaveBeenCalledWith('/sdwan/status');
      expect(result).toEqual(mockStatus);
    });

    it('handles error status', async () => {
      const mockStatus = {
        service: 'SASE Orchestrator API',
        status: 'error',
        clusters: { total: 5, active: 2 },
        clients: { total: 20, active: 5 },
        meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
      };
      const mockResponse = { data: mockStatus };
      mockApiClient.get.mockResolvedValue(mockResponse);

      const result = await getStatus();

      expect(result.status).toBe('error');
    });
  });
});
