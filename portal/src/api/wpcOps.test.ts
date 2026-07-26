import * as wpcOps from './wpcOps';
import apiClient from './client';

jest.mock('./client');

const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

interface MockResponse<T> {
  data: T;
}

describe('wpcOps API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Alert Rules', () => {
    it('lists alert rules', async () => {
      const mockRules = [
        {
          id: 'rule-1',
          name: 'High Latency',
          metric: 'latency_ms',
          comparator: 'gt' as const,
          threshold: 500,
          window_seconds: 300,
          enabled: true,
          created_at: '2026-07-15T00:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: { rules: mockRules, meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' } },
      } as MockResponse<wpcOps.AlertRulesResponse>);

      const result = await wpcOps.listAlertRules();
      expect(result).toEqual(mockRules);
      expect(mockApiClient.get).toHaveBeenCalledWith('/perftest_cluster/alerts/rules');
    });

    it('creates an alert rule', async () => {
      const newRule = {
        id: 'rule-2',
        name: 'Low Throughput',
        metric: 'throughput',
        comparator: 'lt' as const,
        threshold: 100,
        window_seconds: 300,
        enabled: true,
        created_at: '2026-07-15T00:00:00Z',
      };

      mockApiClient.post.mockResolvedValue({ data: newRule } as Record<string, unknown>);

      const result = await wpcOps.createAlertRule({
        name: 'Low Throughput',
        metric: 'throughput',
        comparator: 'lt',
        threshold: 100,
      });

      expect(result).toEqual(newRule);
      expect(mockApiClient.post).toHaveBeenCalledWith(
        '/perftest_cluster/alerts/rules',
        expect.objectContaining({ name: 'Low Throughput' })
      );
    });

    it('deletes an alert rule', async () => {
      mockApiClient.delete.mockResolvedValue({} as Record<string, unknown>);

      await wpcOps.deleteAlertRule('rule-1');
      expect(mockApiClient.delete).toHaveBeenCalledWith('/perftest_cluster/alerts/rules/rule-1');
    });
  });

  describe('Alert Events', () => {
    it('lists alert events', async () => {
      const mockEvents = [
        {
          id: 'evt-1',
          rule_id: 'rule-1',
          device_id: 'dev-1',
          observed_value: 600,
          fired_at: '2026-07-15T10:00:00Z',
          notified: true,
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: { events: mockEvents, meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' } },
      } as Record<string, unknown>);

      const result = await wpcOps.listAlertEvents();
      expect(result).toEqual(mockEvents);
      expect(mockApiClient.get).toHaveBeenCalledWith('/perftest_cluster/alerts/events');
    });
  });

  describe('Alert Channels', () => {
    it('lists alert channels', async () => {
      const mockChannels = [
        {
          id: 'ch-1',
          name: 'Default Email',
          kind: 'email' as const,
          config: { to: ['admin@test.com'] },
          enabled: true,
          created_at: '2026-07-15T00:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: { channels: mockChannels, meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' } },
      } as Record<string, unknown>);

      const result = await wpcOps.listAlertChannels();
      expect(result).toEqual(mockChannels);
      expect(mockApiClient.get).toHaveBeenCalledWith('/perftest_cluster/alerts/channels');
    });

    it('creates an alert channel', async () => {
      const newChannel = {
        id: 'ch-2',
        name: 'Slack Webhook',
        kind: 'webhook' as const,
        config: { url: 'https://hooks.slack.com/...' },
        enabled: true,
        created_at: '2026-07-15T00:00:00Z',
      };

      mockApiClient.post.mockResolvedValue({ data: newChannel } as Record<string, unknown>);

      const result = await wpcOps.createAlertChannel({
        name: 'Slack Webhook',
        kind: 'webhook',
        config: { url: 'https://hooks.slack.com/...' },
      });

      expect(result).toEqual(newChannel);
      expect(mockApiClient.post).toHaveBeenCalled();
    });

    it('deletes an alert channel', async () => {
      mockApiClient.delete.mockResolvedValue({} as Record<string, unknown>);

      await wpcOps.deleteAlertChannel('ch-1');
      expect(mockApiClient.delete).toHaveBeenCalledWith('/perftest_cluster/alerts/channels/ch-1');
    });
  });

  describe('Scheduled Tests', () => {
    it('lists scheduled tests', async () => {
      const mockTests = [
        {
          id: 'job-1',
          device_id: 'dev-1',
          test_type: 'latency',
          target: 'https://example.com',
          interval_seconds: 300,
          enabled: true,
          next_run_at: '2026-07-15T11:00:00Z',
          created_at: '2026-07-15T00:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: { jobs: mockTests, meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' } },
      } as Record<string, unknown>);

      const result = await wpcOps.listScheduledTests();
      expect(result).toEqual(mockTests);
    });

    it('creates a scheduled test', async () => {
      const newTest = {
        id: 'job-2',
        device_id: 'dev-2',
        test_type: 'throughput',
        target: 'https://api.example.com',
        interval_seconds: 600,
        enabled: true,
        next_run_at: '2026-07-15T11:00:00Z',
        created_at: '2026-07-15T00:00:00Z',
      };

      mockApiClient.post.mockResolvedValue({ data: newTest } as Record<string, unknown>);

      const result = await wpcOps.createScheduledTest({
        device_id: 'dev-2',
        test_type: 'throughput',
        target: 'https://api.example.com',
        interval_seconds: 600,
      });

      expect(result).toEqual(newTest);
    });

    it('updates scheduled test enabled status', async () => {
      const updated = {
        id: 'job-1',
        device_id: 'dev-1',
        test_type: 'latency',
        target: 'https://example.com',
        interval_seconds: 300,
        enabled: false,
        next_run_at: '2026-07-15T11:00:00Z',
        created_at: '2026-07-15T00:00:00Z',
      };

      mockApiClient.patch.mockResolvedValue({ data: updated } as Record<string, unknown>);

      const result = await wpcOps.updateScheduledTest('job-1', { enabled: false });
      expect(result).toEqual(updated);
    });

    it('deletes a scheduled test', async () => {
      mockApiClient.delete.mockResolvedValue({} as Record<string, unknown>);

      await wpcOps.deleteScheduledTest('job-1');
      expect(mockApiClient.delete).toHaveBeenCalledWith(
        '/perftest_cluster/scheduled-tests/job-1'
      );
    });
  });

  describe('AutoPerf Policies', () => {
    it('lists autoperf policies', async () => {
      const mockPolicies = [
        {
          id: 'policy-1',
          tenant: 'tenant-1',
          name: 'Production Monitor',
          device_id: 'dev-1',
          target: '192.168.1.1',
          t1_interval_seconds: 300,
          t2_interval_seconds: 120,
          t3_interval_seconds: 60,
          deescalate_after_clean: 3,
          enabled: true,
          created_at: '2026-07-15T00:00:00Z',
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: { policies: mockPolicies },
      } as Record<string, unknown>);

      const result = await wpcOps.listAutoPerfPolicies();
      expect(result).toEqual(mockPolicies);
    });

    it('creates an autoperf policy', async () => {
      const newPolicy = {
        id: 'policy-2',
        tenant: 'tenant-1',
        name: 'Staging Monitor',
        device_id: 'dev-2',
        target: '192.168.1.2',
        t1_interval_seconds: 300,
        t2_interval_seconds: 120,
        t3_interval_seconds: 60,
        deescalate_after_clean: 3,
        enabled: true,
        created_at: '2026-07-15T00:00:00Z',
      };

      mockApiClient.post.mockResolvedValue({ data: newPolicy } as Record<string, unknown>);

      const result = await wpcOps.createAutoPerfPolicy({
        name: 'Staging Monitor',
        device_id: 'dev-2',
        target: '192.168.1.2',
      });

      expect(result).toEqual(newPolicy);
    });

    it('deletes an autoperf policy', async () => {
      mockApiClient.delete.mockResolvedValue({} as Record<string, unknown>);

      await wpcOps.deleteAutoPerfPolicy('policy-1');
      expect(mockApiClient.delete).toHaveBeenCalledWith(
        '/perftest_cluster/autoperf/policies/policy-1'
      );
    });

    it('gets autoperf policy state', async () => {
      const mockState = {
        current_tier: 'T1' as const,
        clean_cycles: 2,
        escalated_at: null,
      };

      mockApiClient.get.mockResolvedValue({ data: mockState } as Record<string, unknown>);

      const result = await wpcOps.getAutoPerfPolicyState('policy-1');
      expect(result).toEqual(mockState);
      expect(mockApiClient.get).toHaveBeenCalledWith(
        '/perftest_cluster/autoperf/policies/policy-1/state'
      );
    });
  });
});
