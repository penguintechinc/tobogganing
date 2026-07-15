import {
  listEndpoints,
  listRuns,
  listRecurringJobs,
  listRegions,
  getEndpoint,
  createEndpoint,
  updateEndpoint,
  deleteEndpoint,
  getRun,
  createRun,
  getLatestMatrix,
  getRunMatrix,
  getMatrixTrends,
  createRecurringJob,
  deleteRecurringJob,
  updateRecurringJob,
  listVisibleNodes,
} from './c2c';
import apiClient from './client';

jest.mock('./client');

describe('c2c API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listEndpoints', () => {
    it('should fetch endpoints from the API', async () => {
      const mockEndpoints = [
        {
          id: 'ep-1',
          region: 'us-west-2',
          name: 'node-1',
          engine_url: 'http://engine:8080',
          target: 'target.com',
          enabled: true,
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          endpoints: mockEndpoints,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listEndpoints();

      expect(result).toEqual(mockEndpoints);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/endpoints');
    });
  });

  describe('getEndpoint', () => {
    it('should fetch a single endpoint by id', async () => {
      const mockEndpoint = {
        id: 'ep-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      };

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: mockEndpoint,
      });

      const result = await getEndpoint('ep-1');

      expect(result).toEqual(mockEndpoint);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/endpoints/ep-1');
    });
  });

  describe('createEndpoint', () => {
    it('should create a new endpoint', async () => {
      const payload = {
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
      };

      const mockEndpoint = { id: 'ep-1', ...payload, enabled: true };

      (apiClient.post as jest.Mock).mockResolvedValue({
        data: mockEndpoint,
      });

      const result = await createEndpoint(payload);

      expect(result).toEqual(mockEndpoint);
      expect(apiClient.post).toHaveBeenCalledWith('/waddleperf_c2c/endpoints', payload);
    });
  });

  describe('updateEndpoint', () => {
    it('should update an endpoint', async () => {
      const updatePayload = { name: 'updated-node' };
      const mockEndpoint = {
        id: 'ep-1',
        region: 'us-west-2',
        name: 'updated-node',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      };

      (apiClient.patch as jest.Mock).mockResolvedValue({
        data: mockEndpoint,
      });

      const result = await updateEndpoint('ep-1', updatePayload);

      expect(result).toEqual(mockEndpoint);
      expect(apiClient.patch).toHaveBeenCalledWith('/waddleperf_c2c/endpoints/ep-1', updatePayload);
    });
  });

  describe('deleteEndpoint', () => {
    it('should delete an endpoint', async () => {
      (apiClient.delete as jest.Mock).mockResolvedValue({});

      await deleteEndpoint('ep-1');

      expect(apiClient.delete).toHaveBeenCalledWith('/waddleperf_c2c/endpoints/ep-1');
    });
  });

  describe('listRuns', () => {
    it('should fetch runs from the API', async () => {
      const mockRuns = [
        {
          id: 'run-1',
          status: 'completed',
          total_pairs: 10,
          created_at: '2026-07-15T00:00:00Z',
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          runs: mockRuns,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listRuns();

      expect(result).toEqual(mockRuns);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/runs');
    });
  });

  describe('getRun', () => {
    it('should fetch a single run by id', async () => {
      const mockRun = {
        id: 'run-1',
        status: 'completed',
        total_pairs: 10,
        created_at: '2026-07-15T00:00:00Z',
      };

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: mockRun,
      });

      const result = await getRun('run-1');

      expect(result).toEqual(mockRun);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/runs/run-1');
    });
  });

  describe('createRun', () => {
    it('should create a new run', async () => {
      const payload = { test_types: ['latency'] };

      (apiClient.post as jest.Mock).mockResolvedValue({
        data: { run_id: 'run-1', total_pairs: 10 },
      });

      const result = await createRun(payload);

      expect(result).toEqual({ run_id: 'run-1', total_pairs: 10 });
      expect(apiClient.post).toHaveBeenCalledWith('/waddleperf_c2c/runs', payload);
    });
  });

  describe('getLatestMatrix', () => {
    it('should fetch latest matrix for test type', async () => {
      const mockMatrix = {
        regions: ['us-west-2', 'us-east-1'],
        cells: [],
      };

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: mockMatrix,
      });

      const result = await getLatestMatrix('latency');

      expect(result).toEqual(mockMatrix);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/matrix/latest', {
        params: { test_type: 'latency' },
      });
    });
  });

  describe('getRunMatrix', () => {
    it('should fetch matrix for a specific run', async () => {
      const mockMatrix = {
        regions: ['us-west-2', 'us-east-1'],
        cells: [],
      };

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: mockMatrix,
      });

      const result = await getRunMatrix('run-1');

      expect(result).toEqual(mockMatrix);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/matrix/runs/run-1');
    });
  });

  describe('getMatrixTrends', () => {
    it('should fetch matrix trends', async () => {
      const mockTrends = [{ timestamp: '2026-07-15T00:00:00Z', value: 50 }];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          source: 'us-west-2',
          dest: 'us-east-1',
          test_type: 'latency',
          trends: mockTrends,
        },
      });

      const result = await getMatrixTrends('us-west-2', 'us-east-1', 'latency');

      expect(result).toEqual(mockTrends);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/matrix/trends', {
        params: { source: 'us-west-2', dest: 'us-east-1', test_type: 'latency' },
      });
    });
  });

  describe('listRecurringJobs', () => {
    it('should fetch recurring jobs from the API', async () => {
      const mockJobs = [
        {
          id: 'job-1',
          job_type: 'matrix_run' as const,
          interval_seconds: 300,
          enabled: true,
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          jobs: mockJobs,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listRecurringJobs();

      expect(result).toEqual(mockJobs);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/recurring');
    });
  });

  describe('createRecurringJob', () => {
    it('should create a recurring job', async () => {
      const payload = {
        job_type: 'matrix_run' as const,
        interval_seconds: 300,
      };

      const mockJob = {
        id: 'job-1',
        ...payload,
        enabled: true,
      };

      (apiClient.post as jest.Mock).mockResolvedValue({
        data: mockJob,
      });

      const result = await createRecurringJob(payload);

      expect(result).toEqual(mockJob);
      expect(apiClient.post).toHaveBeenCalledWith('/waddleperf_c2c/recurring', payload);
    });
  });

  describe('deleteRecurringJob', () => {
    it('should delete a recurring job', async () => {
      (apiClient.delete as jest.Mock).mockResolvedValue({});

      await deleteRecurringJob('job-1');

      expect(apiClient.delete).toHaveBeenCalledWith('/waddleperf_c2c/recurring/job-1');
    });
  });

  describe('updateRecurringJob', () => {
    it('should update recurring job enabled status', async () => {
      (apiClient.patch as jest.Mock).mockResolvedValue({
        data: { enabled: false },
      });

      const result = await updateRecurringJob('job-1', false);

      expect(result.id).toBe('job-1');
      expect(result.enabled).toBe(false);
      expect(apiClient.patch).toHaveBeenCalledWith('/waddleperf_c2c/recurring/job-1', {
        enabled: false,
      });
    });
  });

  describe('listRegions', () => {
    it('should fetch regions from the API', async () => {
      const mockRegions = [
        {
          region: 'us-west-2',
          node_count: 5,
          healthy_count: 4,
          providers: ['aws'],
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          regions: mockRegions,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listRegions();

      expect(result).toEqual(mockRegions);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/regions');
    });
  });

  describe('listVisibleNodes', () => {
    it('should fetch visible nodes', async () => {
      const mockNodes = [
        {
          id: 'node-1',
          region: 'us-west-2',
          name: 'node-1',
          engine_url: 'http://engine:8080',
          target: 'target.com',
          enabled: true,
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          nodes: mockNodes,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listVisibleNodes();

      expect(result).toEqual(mockNodes);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/regions/nodes', {
        params: {},
      });
    });

    it('should fetch visible nodes filtered by region', async () => {
      const mockNodes = [
        {
          id: 'node-1',
          region: 'us-west-2',
          name: 'node-1',
          engine_url: 'http://engine:8080',
          target: 'target.com',
          enabled: true,
        },
      ];

      (apiClient.get as jest.Mock).mockResolvedValue({
        data: {
          nodes: mockNodes,
          meta: { version: 1, timestamp: '2026-07-15T00:00:00Z' },
        },
      });

      const result = await listVisibleNodes('us-west-2');

      expect(result).toEqual(mockNodes);
      expect(apiClient.get).toHaveBeenCalledWith('/waddleperf_c2c/regions/nodes', {
        params: { region: 'us-west-2' },
      });
    });
  });
});
