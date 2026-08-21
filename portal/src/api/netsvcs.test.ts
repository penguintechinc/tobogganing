import apiClient from './client';
import {
  listZones,
  createZone,
  getZone,
  updateZone,
  deleteZone,
  listRecords,
  createRecord,
  updateRecord,
  deleteRecord,
  listDnsServers,
  getDnsServer,
  deleteDnsServer,
  getDnsServerMetrics,
  getAnalyticsSummary,
  getAnalyticsQueries,
  getAnalyticsPerformance,
  getAnalyticsServers,
} from './netsvcs';

jest.mock('./client');
const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

const meta = { version: 1, timestamp: '2026-08-20T10:00:00Z' };

describe('netsvcs API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('zones', () => {
    it('lists zones', async () => {
      const zones = [
        {
          id: 'z1',
          name: 'example.com',
          visibility: 'public',
          description: null,
          created_at: meta.timestamp,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { zones, meta } });

      const result = await listZones();

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/zones');
      expect(result).toEqual(zones);
    });

    it('creates a zone', async () => {
      const zone = {
        id: 'z1',
        name: 'example.com',
        visibility: 'public',
        description: null,
        created_at: meta.timestamp,
      };
      mockApiClient.post.mockResolvedValue({ data: zone });

      const result = await createZone({ name: 'example.com' });

      expect(mockApiClient.post).toHaveBeenCalledWith('/netsvcs/zones', { name: 'example.com' });
      expect(result).toEqual(zone);
    });

    it('gets a zone', async () => {
      const zone = {
        id: 'z1',
        name: 'example.com',
        visibility: 'public',
        description: null,
        created_at: meta.timestamp,
      };
      mockApiClient.get.mockResolvedValue({ data: zone });

      const result = await getZone('z1');

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/zones/z1');
      expect(result).toEqual(zone);
    });

    it('updates a zone', async () => {
      const zone = {
        id: 'z1',
        name: 'updated.com',
        visibility: 'private',
        description: null,
        created_at: meta.timestamp,
      };
      mockApiClient.put.mockResolvedValue({ data: zone });

      const result = await updateZone('z1', { name: 'updated.com', visibility: 'private' });

      expect(mockApiClient.put).toHaveBeenCalledWith('/netsvcs/zones/z1', {
        name: 'updated.com',
        visibility: 'private',
      });
      expect(result).toEqual(zone);
    });

    it('deletes a zone', async () => {
      const message = { message: 'Zone deleted successfully', meta };
      mockApiClient.delete.mockResolvedValue({ data: message });

      const result = await deleteZone('z1');

      expect(mockApiClient.delete).toHaveBeenCalledWith('/netsvcs/zones/z1');
      expect(result).toEqual(message);
    });
  });

  describe('records', () => {
    it('lists records for a zone', async () => {
      const records = [
        {
          id: 'r1',
          name: 'www',
          type: 'A',
          value: '1.2.3.4',
          ttl: 300,
          created_at: meta.timestamp,
          priority: null,
          weight: null,
          port: null,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { records, meta } });

      const result = await listRecords('z1');

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/zones/z1/records');
      expect(result).toEqual(records);
    });

    it('creates a record', async () => {
      const record = {
        id: 'r1',
        name: 'www',
        type: 'A',
        value: '1.2.3.4',
        ttl: 300,
        created_at: meta.timestamp,
        priority: null,
        weight: null,
        port: null,
      };
      mockApiClient.post.mockResolvedValue({ data: record });

      const result = await createRecord('z1', { name: 'www', type: 'A', value: '1.2.3.4' });

      expect(mockApiClient.post).toHaveBeenCalledWith('/netsvcs/zones/z1/records', {
        name: 'www',
        type: 'A',
        value: '1.2.3.4',
      });
      expect(result).toEqual(record);
    });

    it('updates a record', async () => {
      const record = {
        id: 'r1',
        name: 'www',
        type: 'A',
        value: '5.6.7.8',
        ttl: 600,
        created_at: meta.timestamp,
        priority: null,
        weight: null,
        port: null,
      };
      mockApiClient.put.mockResolvedValue({ data: record });

      const result = await updateRecord('z1', 'r1', { value: '5.6.7.8', ttl: 600 });

      expect(mockApiClient.put).toHaveBeenCalledWith('/netsvcs/zones/z1/records/r1', {
        value: '5.6.7.8',
        ttl: 600,
      });
      expect(result).toEqual(record);
    });

    it('deletes a record', async () => {
      const message = { message: 'Record deleted successfully', meta };
      mockApiClient.delete.mockResolvedValue({ data: message });

      const result = await deleteRecord('z1', 'r1');

      expect(mockApiClient.delete).toHaveBeenCalledWith('/netsvcs/zones/z1/records/r1');
      expect(result).toEqual(message);
    });
  });

  describe('dns servers', () => {
    it('lists dns servers', async () => {
      const servers = [
        {
          id: 's1',
          name: 'resolver-1',
          status: 'online',
          version: '1.0.0',
          region: 'us-east-1',
          hostname: 'resolver-1.internal',
          last_heartbeat: meta.timestamp,
          created_at: meta.timestamp,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { servers, meta } });

      const result = await listDnsServers();

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/dns-servers');
      expect(result).toEqual(servers);
    });

    it('gets a dns server', async () => {
      const server = {
        id: 's1',
        name: 'resolver-1',
        status: 'online',
        version: '1.0.0',
        region: 'us-east-1',
        hostname: 'resolver-1.internal',
        last_heartbeat: meta.timestamp,
        created_at: meta.timestamp,
      };
      mockApiClient.get.mockResolvedValue({ data: server });

      const result = await getDnsServer('s1');

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/dns-servers/s1');
      expect(result).toEqual(server);
    });

    it('deletes a dns server', async () => {
      const message = { message: 'DNS server deleted successfully', meta };
      mockApiClient.delete.mockResolvedValue({ data: message });

      const result = await deleteDnsServer('s1');

      expect(mockApiClient.delete).toHaveBeenCalledWith('/netsvcs/dns-servers/s1');
      expect(result).toEqual(message);
    });

    it('fetches dns server metrics with default hours', async () => {
      const metrics = [
        {
          server_id: 's1',
          timestamp: meta.timestamp,
          queries_total: 1000,
          cache_hits: 800,
          errors: 5,
          avg_response_ms: 12.5,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { metrics, meta } });

      const result = await getDnsServerMetrics('s1');

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/dns-servers/s1/metrics', {
        params: { hours: 24 },
      });
      expect(result).toEqual(metrics);
    });

    it('fetches dns server metrics with custom hours', async () => {
      mockApiClient.get.mockResolvedValue({ data: { metrics: [], meta } });

      await getDnsServerMetrics('s1', 6);

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/dns-servers/s1/metrics', {
        params: { hours: 6 },
      });
    });
  });

  describe('analytics', () => {
    it('fetches summary metrics', async () => {
      const metrics = [
        { key: 'zones', value: 3 },
        { key: 'records', value: 12 },
        { key: 'servers', value: 2 },
        { key: 'queries_24h', value: 5000 },
      ];
      mockApiClient.get.mockResolvedValue({ data: { metrics, meta } });

      const result = await getAnalyticsSummary();

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/analytics/summary');
      expect(result).toEqual(metrics);
    });

    it('fetches queries analytics', async () => {
      const data = {
        total_queries: 5000,
        total_cache_hits: 4000,
        total_errors: 10,
        cache_hit_rate: 80,
        timeline: [{ timestamp: meta.timestamp, queries: 100 }],
        meta,
      };
      mockApiClient.get.mockResolvedValue({ data });

      const result = await getAnalyticsQueries();

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/analytics/queries', {
        params: { hours: 24 },
      });
      expect(result).toEqual(data);
    });

    it('fetches performance analytics', async () => {
      const metrics = [{ metric: 'avg_response_ms', value: 12.5 }];
      mockApiClient.get.mockResolvedValue({ data: { metrics, meta } });

      const result = await getAnalyticsPerformance(12);

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/analytics/performance', {
        params: { hours: 12 },
      });
      expect(result).toEqual(metrics);
    });

    it('fetches per-server analytics', async () => {
      const servers = [
        {
          server_id: 's1',
          server_name: 'resolver-1',
          queries: 1000,
          cache_hits: 800,
          errors: 5,
          avg_response_ms: 12.5,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { servers, meta } });

      const result = await getAnalyticsServers();

      expect(mockApiClient.get).toHaveBeenCalledWith('/netsvcs/analytics/servers', {
        params: { hours: 24 },
      });
      expect(result).toEqual(servers);
    });
  });
});
