import apiClient from './client';
import {
  listClusters,
  listClients,
  getStatus,
  listBlockPages,
  createBlockPage,
  updateBlockPage,
  publishBlockPage,
  previewBlockPage,
  listBlockRoutes,
  upsertBlockRoutes,
  type BlockPage,
} from './sase';

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

  const mockPage: BlockPage = {
    id: 'page-1',
    tenant: 'tenant-1',
    name: 'Test Page',
    markdown: '# Test',
    status: 'draft',
    version: 1,
    created_by: 'user-1',
    updated_by: null,
    created_at: '2026-07-15T10:00:00Z',
    updated_at: '2026-07-15T10:00:00Z',
  };

  describe('listBlockPages', () => {
    it('fetches block pages from the API', async () => {
      mockApiClient.get.mockResolvedValue({ data: { pages: [mockPage] } });

      const result = await listBlockPages();

      expect(mockApiClient.get).toHaveBeenCalledWith('/blockpages/pages');
      expect(result).toEqual([mockPage]);
    });
  });

  describe('createBlockPage', () => {
    it('posts a new block page', async () => {
      mockApiClient.post.mockResolvedValue({ data: mockPage });

      const result = await createBlockPage('Test Page', '# Test');

      expect(mockApiClient.post).toHaveBeenCalledWith('/blockpages/pages', {
        name: 'Test Page',
        markdown: '# Test',
      });
      expect(result).toEqual(mockPage);
    });
  });

  describe('updateBlockPage', () => {
    it('puts updated markdown for a page', async () => {
      mockApiClient.put.mockResolvedValue({ data: { ...mockPage, markdown: '# Updated' } });

      const result = await updateBlockPage('page-1', '# Updated');

      expect(mockApiClient.put).toHaveBeenCalledWith('/blockpages/pages/page-1', {
        markdown: '# Updated',
      });
      expect(result.markdown).toBe('# Updated');
    });
  });

  describe('publishBlockPage', () => {
    it('posts to the publish endpoint', async () => {
      mockApiClient.post.mockResolvedValue({ data: { ...mockPage, status: 'live' } });

      const result = await publishBlockPage('page-1');

      expect(mockApiClient.post).toHaveBeenCalledWith('/blockpages/pages/page-1/publish');
      expect(result.status).toBe('live');
    });
  });

  describe('previewBlockPage', () => {
    it('posts with provided variables', async () => {
      mockApiClient.post.mockResolvedValue({
        data: { html: '<h1>Test</h1>', variables: { category: 'malware' } },
      });

      const result = await previewBlockPage('page-1', { category: 'malware' });

      expect(mockApiClient.post).toHaveBeenCalledWith('/blockpages/pages/page-1/preview', {
        variables: { category: 'malware' },
      });
      expect(result.html).toBe('<h1>Test</h1>');
    });

    it('defaults to empty variables when none provided', async () => {
      mockApiClient.post.mockResolvedValue({
        data: { html: '<p></p>', variables: {} },
      });

      await previewBlockPage('page-1');

      expect(mockApiClient.post).toHaveBeenCalledWith('/blockpages/pages/page-1/preview', {
        variables: {},
      });
    });
  });

  describe('listBlockRoutes', () => {
    it('fetches block routes from the API', async () => {
      const mockRoute = {
        id: 'route-1',
        tenant: 'tenant-1',
        source_type: 'category:malware',
        destination_kind: 'page' as const,
        page_id: 'page-1',
        external_url: null,
        created_at: '2026-07-15T10:00:00Z',
        created_by: 'user-1',
        updated_by: null,
        ticket: null,
        notes: null,
        expiry: null,
        review_date: null,
        scope: null,
        risk: null,
      };
      mockApiClient.get.mockResolvedValue({ data: { routes: [mockRoute] } });

      const result = await listBlockRoutes();

      expect(mockApiClient.get).toHaveBeenCalledWith('/blockpages/routes');
      expect(result).toEqual([mockRoute]);
    });
  });

  describe('upsertBlockRoutes', () => {
    it('puts routes payload and returns the result', async () => {
      const routesPayload = [
        {
          source_type: 'category:malware',
          destination_kind: 'page' as const,
          page_id: 'page-1',
        },
      ];
      mockApiClient.put.mockResolvedValue({ data: { routes: [] } });

      const result = await upsertBlockRoutes(routesPayload);

      expect(mockApiClient.put).toHaveBeenCalledWith('/blockpages/routes', {
        routes: routesPayload,
      });
      expect(result).toEqual([]);
    });
  });
});
