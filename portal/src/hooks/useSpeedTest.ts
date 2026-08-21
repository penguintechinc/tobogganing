import { useCallback, useRef, useState } from 'react';
import {
  runPingTest,
  runDownloadTest,
  runUploadTest,
  submitSpeedTestResult,
  type PingResult,
  type DownloadResult,
  type UploadResult,
} from '../api/speedtest';

export type SpeedTestPhase = 'idle' | 'ping' | 'download' | 'upload' | 'complete' | 'error';

export interface SpeedTestChartPoint {
  timestamp: number;
  label: string;
  mbps: number;
}

export interface SpeedTestHookState {
  phase: SpeedTestPhase;
  ping: PingResult | null;
  download: DownloadResult | null;
  upload: UploadResult | null;
  series: SpeedTestChartPoint[];
  error: string | null;
  run: (serverUrl: string, sizeMB?: number) => Promise<void>;
  reset: () => void;
}

/**
 * Orchestrates a full self-service speed test (ping -> download -> upload)
 * against a user-supplied engine URL, accumulating a time series of
 * instantaneous throughput samples for a realtime chart as each phase runs.
 */
export function useSpeedTest(): SpeedTestHookState {
  const [phase, setPhase] = useState<SpeedTestPhase>('idle');
  const [ping, setPing] = useState<PingResult | null>(null);
  const [download, setDownload] = useState<DownloadResult | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [series, setSeries] = useState<SpeedTestChartPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const seriesRef = useRef<SpeedTestChartPoint[]>([]);

  const appendSample = useCallback((label: string, mbps: number) => {
    seriesRef.current = [...seriesRef.current, { timestamp: Date.now(), label, mbps }].slice(-200);
    setSeries(seriesRef.current);
  }, []);

  const reset = useCallback(() => {
    console.log('[useSpeedTest] Resetting');
    setPhase('idle');
    setPing(null);
    setDownload(null);
    setUpload(null);
    setSeries([]);
    seriesRef.current = [];
    setError(null);
  }, []);

  const run = useCallback(
    async (serverUrl: string, sizeMB = 10) => {
      console.log('[useSpeedTest] Starting test', { serverUrl, sizeMB });
      seriesRef.current = [];
      setSeries([]);
      setError(null);

      try {
        setPhase('ping');
        const pingResult = await runPingTest(serverUrl);
        setPing(pingResult);
        appendSample('ping', pingResult.latencyMs);

        setPhase('download');
        const downloadResult = await runDownloadTest(serverUrl, sizeMB, (sample) =>
          appendSample('download', sample.mbps)
        );
        setDownload(downloadResult);

        setPhase('upload');
        const uploadResult = await runUploadTest(serverUrl, sizeMB, (sample) =>
          appendSample('upload', sample.mbps)
        );
        setUpload(uploadResult);

        setPhase('complete');

        try {
          await submitSpeedTestResult(serverUrl, {
            download_mbps: downloadResult.mbps,
            upload_mbps: uploadResult.mbps,
            latency_ms: pingResult.latencyMs,
            jitter_ms: pingResult.jitterMs,
            server_url: serverUrl,
          });
        } catch (submitErr) {
          // Non-fatal: the on-screen result is already complete even if
          // persisting it server-side fails.
          console.error('[useSpeedTest] Failed to submit result', submitErr);
        }
      } catch (err) {
        console.error('[useSpeedTest] Test failed', err);
        setError(err instanceof Error ? err.message : 'Speed test failed');
        setPhase('error');
      }
    },
    [appendSample]
  );

  return { phase, ping, download, upload, series, error, run, reset };
}
