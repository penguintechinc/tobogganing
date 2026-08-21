import { renderHook, act, waitFor } from '@testing-library/react';
import { useLiveTest } from './useLiveTest';
import * as client from '../api/client';

jest.mock('../api/client');
const mockApiClient = client as jest.Mocked<typeof client>;

describe('useLiveTest', () => {
  let mockWs: {
    send: jest.Mock;
    close: jest.Mock;
    onopen?: () => void;
    onmessage?: (event: MessageEvent) => void;
    onerror?: () => void;
    onclose?: () => void;
  };

  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    mockWs = {
      send: jest.fn(),
      close: jest.fn(),
    };

    (global.WebSocket as unknown as jest.Mock) = jest.fn(() => mockWs);
    mockApiClient.default.post = jest.fn().mockResolvedValue({});
    sessionStorage.setItem('access_token', 'test-token-123');
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('initializes with closed status', () => {
    const { result } = renderHook(() => useLiveTest());

    expect(result.current.status).toBe('closed');
    expect(result.current.events).toEqual([]);
    expect(result.current.series).toEqual([]);
  });

  it('connects with token in the subprotocol header, never the URL', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await waitFor(() => {
      expect(global.WebSocket).toHaveBeenCalled();
    });

    const call = (global.WebSocket as unknown as jest.Mock).mock.calls[0];
    const wsUrl = call?.[0] as string;
    const subprotocols = call?.[1] as string[];
    // URL carries no credential
    expect(wsUrl).toContain('/api/v1/perftest_cluster/live-test/stream');
    expect(wsUrl).not.toContain('token');
    expect(wsUrl).not.toContain('test-token-123');
    // Token rides in the Sec-WebSocket-Protocol handshake header
    expect(subprotocols).toEqual(['tobogganing-bearer', 'test-token-123']);
  });

  it('posts to /live-test/run on start', async () => {
    const { result } = renderHook(() => useLiveTest());
    const payload = {
      device_id: 'device-1',
      test_type: 'http',
      target: 'example.com',
      params: { port: 80 },
    };

    await act(async () => {
      await result.current.start(payload);
    });

    await waitFor(() => {
      expect(mockApiClient.default.post).toHaveBeenCalledWith(
        '/perftest_cluster/live-test/run',
        expect.objectContaining({
          device_id: 'device-1',
          test_type: 'http',
          target: 'example.com',
          params: { port: 80 },
        })
      );
    });
  });

  it('handles WebSocket open event', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
    });

    expect(result.current.status).toBe('open');
  });

  it('parses and stores test_started event', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: JSON.stringify({
              event: 'test_started',
              data: { message: 'Test started' },
            }),
          })
        );
      }
    });

    expect(result.current.events.length).toBe(1);
    const firstEvent = result.current.events[0];
    expect(firstEvent).toBeDefined();
    if (firstEvent) {
      expect(firstEvent.event).toBe('test_started');
    }
  });

  it('parses test_complete and adds series point', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: JSON.stringify({
              event: 'test_complete',
              data: {
                status: 'success',
                result: { latency: 150, throughput: 1000 },
              },
            }),
          })
        );
      }
    });

    expect(result.current.events.length).toBe(1);
    expect(result.current.series.length).toBe(1);
    const point = result.current.series[0];
    expect(point).toBeDefined();
    if (point) {
      expect(point.latency).toBe(150);
      expect(point.throughput).toBe(1000);
    }
  });

  it('extracts latency from result if present', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: JSON.stringify({
              event: 'test_complete',
              data: { result: { latency: 200 } },
            }),
          })
        );
      }
    });

    const point = result.current.series[0];
    expect(point).toBeDefined();
    if (point) {
      expect(point.latency).toBe(200);
      expect(point.throughput).toBeUndefined();
    }
  });

  it('caps series buffer at 500 points', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
    });

    // Add 510 points
    for (let i = 0; i < 510; i++) {
      await act(async () => {
        if (mockWs.onmessage) {
          mockWs.onmessage(
            new MessageEvent('message', {
              data: JSON.stringify({
                event: 'test_complete',
                data: { result: { latency: 100 + i } },
              }),
            })
          );
        }
      });
    }

    expect(result.current.series.length).toBe(500);
    // Oldest points should be removed (first point should be latency 110)
    const firstPoint = result.current.series[0];
    expect(firstPoint).toBeDefined();
    if (firstPoint) {
      expect(firstPoint.latency).toBe(110);
    }
  });

  it('handles error event', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: JSON.stringify({
              event: 'error',
              data: { message: 'Test failed' },
            }),
          })
        );
      }
    });

    expect(result.current.events.length).toBe(1);
    const firstEvent = result.current.events[0];
    expect(firstEvent).toBeDefined();
    if (firstEvent) {
      expect(firstEvent.event).toBe('error');
    }
  });

  it('handles invalid JSON in message', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: 'invalid json',
          })
        );
      }
    });

    expect(consoleErrorSpy).toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });

  it('handles WebSocket error', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onerror) mockWs.onerror();
    });

    expect(result.current.status).toBe('error');
  });

  it('handles WebSocket close', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onclose) mockWs.onclose();
    });

    expect(result.current.status).toBe('closed');
  });

  it('closes WebSocket on unmount', async () => {
    const { result, unmount } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
    });

    unmount();

    expect(mockWs.close).toHaveBeenCalled();
  });

  it('resets state', async () => {
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    await act(async () => {
      if (mockWs.onopen) mockWs.onopen();
      if (mockWs.onmessage) {
        mockWs.onmessage(
          new MessageEvent('message', {
            data: JSON.stringify({
              event: 'test_complete',
              data: { result: { latency: 150 } },
            }),
          })
        );
      }
    });

    expect(result.current.events.length).toBeGreaterThan(0);
    expect(result.current.series.length).toBeGreaterThan(0);

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('closed');
    expect(result.current.events).toEqual([]);
    expect(result.current.series).toEqual([]);
    expect(mockWs.close).toHaveBeenCalled();
  });

  it('sets error status when no access token', async () => {
    sessionStorage.clear();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      await result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    expect(result.current.status).toBe('error');
    consoleErrorSpy.mockRestore();
  });

  it('handles start error gracefully', async () => {
    mockApiClient.default.post = jest.fn().mockRejectedValue(new Error('API error'));
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    const { result } = renderHook(() => useLiveTest());

    await act(async () => {
      await result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    expect(result.current.status).toBe('error');
    consoleErrorSpy.mockRestore();
  });

  it('handles connectWebSocket when no token available', async () => {
    sessionStorage.clear();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    const { result } = renderHook(() => useLiveTest());

    // Manually call connectWebSocket by using start
    await act(async () => {
      result.current.start({
        device_id: 'device-1',
        test_type: 'http',
        target: 'example.com',
      });
    });

    // Check that error status is set because no token
    expect(result.current.status).toBe('error');
    consoleErrorSpy.mockRestore();
  });
});
