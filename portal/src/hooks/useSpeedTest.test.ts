import { renderHook, act, waitFor } from '@testing-library/react';
import { useSpeedTest } from './useSpeedTest';
import * as speedtestApi from '../api/speedtest';

jest.mock('../api/speedtest');

const mockApi = speedtestApi as jest.Mocked<typeof speedtestApi>;

describe('useSpeedTest', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('initializes idle with empty results', () => {
    const { result } = renderHook(() => useSpeedTest());

    expect(result.current.phase).toBe('idle');
    expect(result.current.ping).toBeNull();
    expect(result.current.download).toBeNull();
    expect(result.current.upload).toBeNull();
    expect(result.current.series).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('runs ping, download, upload in order and lands on complete', async () => {
    mockApi.runPingTest.mockResolvedValue({ latencyMs: 12, jitterMs: 1, samples: [12] });
    mockApi.runDownloadTest.mockImplementation(async (_url, _size, onSample) => {
      onSample?.({ timestamp: Date.now(), mbps: 50 });
      return { mbps: 100, bytes: 1_000_000, durationMs: 80 };
    });
    mockApi.runUploadTest.mockImplementation(async (_url, _size, onSample) => {
      onSample?.({ timestamp: Date.now(), mbps: 25 });
      return { mbps: 40, bytes: 500_000, durationMs: 100 };
    });
    mockApi.submitSpeedTestResult.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSpeedTest());

    await act(async () => {
      await result.current.run('https://engine.example.com');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    expect(result.current.ping).toEqual({ latencyMs: 12, jitterMs: 1, samples: [12] });
    expect(result.current.download?.mbps).toBe(100);
    expect(result.current.upload?.mbps).toBe(40);
    expect(result.current.series.length).toBeGreaterThanOrEqual(3); // ping + download sample + upload sample
    expect(mockApi.submitSpeedTestResult).toHaveBeenCalledWith('https://engine.example.com', {
      download_mbps: 100,
      upload_mbps: 40,
      latency_ms: 12,
      jitter_ms: 1,
      server_url: 'https://engine.example.com',
    });
  });

  it('sets error phase when ping fails', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockApi.runPingTest.mockRejectedValue(new Error('unreachable'));

    const { result } = renderHook(() => useSpeedTest());

    await act(async () => {
      await result.current.run('https://engine.example.com');
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('unreachable');
    consoleErrorSpy.mockRestore();
  });

  it('completes even if submitting the result fails', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockApi.runPingTest.mockResolvedValue({ latencyMs: 10, jitterMs: 0, samples: [10] });
    mockApi.runDownloadTest.mockResolvedValue({ mbps: 90, bytes: 1, durationMs: 1 });
    mockApi.runUploadTest.mockResolvedValue({ mbps: 30, bytes: 1, durationMs: 1 });
    mockApi.submitSpeedTestResult.mockRejectedValue(new Error('save failed'));

    const { result } = renderHook(() => useSpeedTest());

    await act(async () => {
      await result.current.run('');
    });

    expect(result.current.phase).toBe('complete');
    consoleErrorSpy.mockRestore();
  });

  it('resets state', async () => {
    mockApi.runPingTest.mockResolvedValue({ latencyMs: 10, jitterMs: 0, samples: [10] });
    mockApi.runDownloadTest.mockResolvedValue({ mbps: 90, bytes: 1, durationMs: 1 });
    mockApi.runUploadTest.mockResolvedValue({ mbps: 30, bytes: 1, durationMs: 1 });
    mockApi.submitSpeedTestResult.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSpeedTest());

    await act(async () => {
      await result.current.run('');
    });

    expect(result.current.phase).toBe('complete');

    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.ping).toBeNull();
    expect(result.current.download).toBeNull();
    expect(result.current.upload).toBeNull();
    expect(result.current.series).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('caps the series buffer at 200 points', async () => {
    mockApi.runPingTest.mockResolvedValue({ latencyMs: 10, jitterMs: 0, samples: [10] });
    mockApi.runDownloadTest.mockImplementation(async (_url, _size, onSample) => {
      for (let i = 0; i < 250; i += 1) {
        onSample?.({ timestamp: Date.now(), mbps: i });
      }
      return { mbps: 90, bytes: 1, durationMs: 1 };
    });
    mockApi.runUploadTest.mockResolvedValue({ mbps: 30, bytes: 1, durationMs: 1 });
    mockApi.submitSpeedTestResult.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSpeedTest());

    await act(async () => {
      await result.current.run('');
    });

    expect(result.current.series.length).toBe(200);
  });
});
