import * as waddleperf from './waddleperf';
import apiClient from './client';

jest.mock('./client');

describe('waddleperf API', () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listDevices', () => {
    it('calls the correct endpoint and returns devices', async () => {
      const mockDevices: waddleperf.Device[] = [
        {
          id: 'd1',
          name: 'Device 1',
          serial: 'SN001',
          hostname: 'host1',
          os: 'Linux',
          org_unit_id: 'ou1',
          status: 'online',
          last_heartbeat: '2026-07-14T10:00:00Z',
          created_at: '2026-07-14T09:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValueOnce({
        data: { devices: mockDevices, meta: { version: 1, timestamp: '' } },
      });

      const result = await waddleperf.listDevices();

      expect(mockApiClient.get).toHaveBeenCalledWith('/perftest_cluster/devices');
      expect(result).toEqual(mockDevices);
    });
  });

  describe('listTests', () => {
    it('calls the correct endpoint and returns tests', async () => {
      const mockTests: waddleperf.Test[] = [
        {
          id: 't1',
          device_id: 'd1',
          test_type: 'latency',
          status: 'completed',
          target: 'http://example.com',
          latency_ms: 100,
          throughput: 1000,
          created_at: '2026-07-14T10:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValueOnce({
        data: { tests: mockTests, meta: { version: 1, timestamp: '' } },
      });

      const result = await waddleperf.listTests();

      expect(mockApiClient.get).toHaveBeenCalledWith('/perftest_cluster/tests');
      expect(result).toEqual(mockTests);
    });
  });

  describe('getStatsSummary', () => {
    it('calls the correct endpoint and returns summary', async () => {
      const mockSummary: waddleperf.StatsSummary = {
        total_tests: 100,
        total_devices: 10,
        success_rate: 0.95,
        avg_latency_ms: 50,
        avg_throughput: 900,
      };

      mockApiClient.get.mockResolvedValueOnce({
        data: { summary: mockSummary, meta: { version: 1, timestamp: '' } },
      });

      const result = await waddleperf.getStatsSummary();

      expect(mockApiClient.get).toHaveBeenCalledWith(
        '/perftest_cluster/stats/summary'
      );
      expect(result).toEqual(mockSummary);
    });
  });

  describe('getStatsTrends', () => {
    it('calls the correct endpoint and returns trends', async () => {
      const mockTrends: waddleperf.TrendDataPoint[] = [
        { timestamp: '2026-07-14T10:00:00Z', value: 95 },
        { timestamp: '2026-07-14T11:00:00Z', value: 94 },
      ];

      mockApiClient.get.mockResolvedValueOnce({
        data: { trends: mockTrends, meta: { version: 1, timestamp: '' } },
      });

      const result = await waddleperf.getStatsTrends();

      expect(mockApiClient.get).toHaveBeenCalledWith(
        '/perftest_cluster/stats/trends'
      );
      expect(result).toEqual(mockTrends);
    });
  });
});
