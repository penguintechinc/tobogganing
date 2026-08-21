const mockGet = jest.fn();
const mockPost = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      get: (...args: unknown[]) => mockGet(...args),
      post: (...args: unknown[]) => mockPost(...args),
    })),
  },
}));

import {
  getSpeedTestInfo,
  runPingTest,
  runDownloadTest,
  runUploadTest,
  submitSpeedTestResult,
  type SpeedTestInfo,
  type UploadApiResponse,
} from './speedtest';

describe('speedtest API', () => {
  let nowSpy: jest.SpyInstance;
  let tick = 0;

  beforeEach(() => {
    jest.clearAllMocks();
    tick = 0;
    // Advance by 100ms per call so duration math is deterministic and > 0.
    nowSpy = jest.spyOn(performance, 'now').mockImplementation(() => {
      tick += 100;
      return tick;
    });
  });

  afterEach(() => {
    nowSpy.mockRestore();
  });

  describe('getSpeedTestInfo', () => {
    it('calls the info endpoint and returns capabilities', async () => {
      const info: SpeedTestInfo = {
        name: 'WaddlePerf SpeedTest',
        version: '1.0.0',
        max_chunk_size_mb: 100,
        default_chunk_size_mb: 10,
        recommended_streams: 6,
        max_streams: 32,
      };
      mockGet.mockResolvedValueOnce({ data: info });

      const result = await getSpeedTestInfo('https://engine.example.com');

      expect(mockGet).toHaveBeenCalledWith('https://engine.example.com/speedtest/info');
      expect(result).toEqual(info);
    });
  });

  describe('runPingTest', () => {
    it('samples the ping endpoint and derives latency + jitter', async () => {
      mockGet.mockResolvedValue({ data: { pong: true, timestamp: 1 } });

      const result = await runPingTest('', 3);

      expect(mockGet).toHaveBeenCalledTimes(3);
      expect(mockGet).toHaveBeenCalledWith('/speedtest/ping');
      expect(result.samples).toHaveLength(3);
      expect(result.latencyMs).toBeGreaterThan(0);
      expect(result.jitterMs).toBeGreaterThanOrEqual(0);
    });

    it('defaults to 5 samples', async () => {
      mockGet.mockResolvedValue({ data: { pong: true, timestamp: 1 } });

      await runPingTest('https://engine.example.com');

      expect(mockGet).toHaveBeenCalledTimes(5);
    });
  });

  describe('runDownloadTest', () => {
    it('measures throughput and emits progress samples', async () => {
      const onSample = jest.fn();
      mockGet.mockImplementationOnce(
        (_url: string, config: { onDownloadProgress?: (e: { loaded: number }) => void }) => {
          config.onDownloadProgress?.({ loaded: 500_000 });
          config.onDownloadProgress?.({ loaded: 1_000_000 });
          return Promise.resolve({ data: new ArrayBuffer(1_000_000) });
        }
      );

      const result = await runDownloadTest('https://engine.example.com', 1, onSample);

      expect(mockGet).toHaveBeenCalledWith(
        'https://engine.example.com/speedtest/download?size=1',
        expect.objectContaining({ responseType: 'arraybuffer' })
      );
      expect(result.bytes).toBe(1_000_000);
      expect(result.mbps).toBeGreaterThan(0);
      expect(onSample).toHaveBeenCalledTimes(2);
      expect(onSample.mock.calls[0]![0].mbps).toBeGreaterThan(0);
    });

    it('works without an onSample callback', async () => {
      mockGet.mockResolvedValueOnce({ data: new ArrayBuffer(1024) });

      const result = await runDownloadTest('', 10);

      expect(result.bytes).toBe(1024);
    });
  });

  describe('runUploadTest', () => {
    it('uploads random bytes and returns server-computed throughput', async () => {
      const onSample = jest.fn();
      const apiResponse: UploadApiResponse = {
        success: true,
        bytes_received: 1_048_576,
        duration_ms: 100,
        throughput_mbps: 83.9,
      };
      mockPost.mockImplementationOnce(
        (
          _url: string,
          _body: Uint8Array,
          config: { onUploadProgress?: (e: { loaded: number }) => void }
        ) => {
          config.onUploadProgress?.({ loaded: 524_288 });
          config.onUploadProgress?.({ loaded: 1_048_576 });
          return Promise.resolve({ data: apiResponse });
        }
      );

      const result = await runUploadTest('https://engine.example.com', 1, onSample);

      expect(mockPost).toHaveBeenCalledWith(
        'https://engine.example.com/speedtest/upload',
        expect.any(Uint8Array),
        expect.objectContaining({ headers: { 'Content-Type': 'application/octet-stream' } })
      );
      expect(result).toEqual({ mbps: 83.9, bytes: 1_048_576, durationMs: 100 });
      expect(onSample).toHaveBeenCalledTimes(2);
    });
  });

  describe('submitSpeedTestResult', () => {
    it('posts the result payload to the engine', async () => {
      mockPost.mockResolvedValueOnce({ data: { success: true } });

      await submitSpeedTestResult('https://engine.example.com', {
        download_mbps: 100,
        upload_mbps: 50,
        latency_ms: 12.5,
        jitter_ms: 1.2,
        server_url: 'https://engine.example.com',
      });

      expect(mockPost).toHaveBeenCalledWith('https://engine.example.com/speedtest/result', {
        download_mbps: 100,
        upload_mbps: 50,
        latency_ms: 12.5,
        jitter_ms: 1.2,
        server_url: 'https://engine.example.com',
      });
    });
  });
});
