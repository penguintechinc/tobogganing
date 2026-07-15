import { useEffect, useRef, useState } from 'react';
import apiClient from '../api/client';

export interface StreamMessage {
  event: 'test_started' | 'test_complete' | 'error';
  data: Record<string, unknown>;
}

export interface SeriesPoint {
  timestamp: number;
  latency?: number;
  throughput?: number;
}

export interface LiveTestHookState {
  status: 'connecting' | 'open' | 'closed' | 'error';
  events: StreamMessage[];
  series: SeriesPoint[];
  start: (payload: {
    device_id: string;
    test_type: string;
    target: string;
    params?: Record<string, unknown>;
  }) => Promise<void>;
  reset: () => void;
}

export function useLiveTest(): LiveTestHookState {
  const [status, setStatus] = useState<'connecting' | 'open' | 'closed' | 'error'>(
    'closed'
  );
  const [events, setEvents] = useState<StreamMessage[]>([]);
  const [series, setSeries] = useState<SeriesPoint[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const seriesBufferRef = useRef<SeriesPoint[]>([]);

  const reset = () => {
    setEvents([]);
    setSeries([]);
    seriesBufferRef.current = [];
    setStatus('closed');
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  const connectWebSocket = () => {
    const token = sessionStorage.getItem('access_token');
    if (!token) {
      console.error('[useLiveTest] No access token found');
      setStatus('error');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/waddleperf_cluster/live-test/stream?token=${encodeURIComponent(token)}`;

    console.log('[useLiveTest] Connecting to WebSocket');
    setStatus('connecting');

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[useLiveTest] WebSocket connected');
      setStatus('open');
      wsRef.current = ws;
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const message: StreamMessage = JSON.parse(event.data);
        console.log(`[useLiveTest] Received ${message.event} event`);

        setEvents((prev) => [...prev, message]);

        // Extract metrics and add to series buffer
        if (message.event === 'test_complete' && message.data.result) {
          const result = message.data.result as Record<string, unknown>;
          const point: SeriesPoint = {
            timestamp: Date.now(),
          };

          if (typeof result.latency === 'number') {
            point.latency = result.latency;
          }
          if (typeof result.throughput === 'number') {
            point.throughput = result.throughput;
          }

          seriesBufferRef.current.push(point);

          // Cap at 500 points
          if (seriesBufferRef.current.length > 500) {
            seriesBufferRef.current.shift();
          }

          setSeries([...seriesBufferRef.current]);
        }
      } catch (err) {
        console.error('[useLiveTest] Failed to parse message', err);
      }
    };

    ws.onerror = () => {
      console.error('[useLiveTest] WebSocket error');
      setStatus('error');
    };

    ws.onclose = () => {
      console.log('[useLiveTest] WebSocket closed');
      setStatus('closed');
      wsRef.current = null;
    };

    wsRef.current = ws;
  };

  const start = async (payload: {
    device_id: string;
    test_type: string;
    target: string;
    params?: Record<string, unknown>;
  }) => {
    console.log('[useLiveTest] Starting test', payload);

    try {
      // First, trigger the HTTP POST to run the test
      await apiClient.post('/waddleperf_cluster/live-test/run', {
        device_id: payload.device_id,
        test_type: payload.test_type,
        target: payload.target,
        params: payload.params || {},
      });

      // Connect to WebSocket to stream progress
      connectWebSocket();
    } catch (err) {
      console.error('[useLiveTest] Failed to start test', err);
      setStatus('error');
    }
  };

  // Clean up WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    status,
    events,
    series,
    start,
    reset,
  };
}
