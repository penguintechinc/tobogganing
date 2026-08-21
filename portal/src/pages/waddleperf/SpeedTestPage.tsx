import React, { Suspense, lazy, useState } from 'react';
import { useSpeedTest } from '../../hooks/useSpeedTest';

const SpeedTestChart = lazy(() => import('../../components/SpeedTestChart'));

function MetricCard({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className="text-2xl font-bold text-amber-400 mt-2">
        {value}
        {value !== '--' && <span className="text-sm ml-1">{unit}</span>}
      </p>
    </div>
  );
}

const phaseLabels: Record<string, string> = {
  idle: 'Ready',
  ping: 'Measuring latency...',
  download: 'Measuring download...',
  upload: 'Measuring upload...',
  complete: 'Complete',
  error: 'Error',
};

/**
 * Self-service browser speed test. Runs ping/download/upload against a
 * user-supplied WaddlePerf test engine URL directly from the browser
 * (unauthenticated, engine-hosted `/speedtest/*` endpoints - see
 * `src/api/speedtest.ts` for the adapter contract) and renders live
 * download/upload Mbps + latency alongside a realtime throughput chart.
 */
export function SpeedTestPage() {
  const { phase, ping, download, upload, series, error, run, reset } = useSpeedTest();
  const [serverUrl, setServerUrl] = useState('');
  const isRunning = phase === 'ping' || phase === 'download' || phase === 'upload';

  const handleStart = async () => {
    console.log('[SpeedTestPage] Starting speed test', { serverUrl: serverUrl || '(same-origin)' });
    await run(serverUrl);
  };

  const handleReset = () => {
    console.log('[SpeedTestPage] Resetting');
    reset();
    setServerUrl('');
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-amber-400 mb-2">Speed Test</h1>
        <p className="text-slate-400">Run a self-service bandwidth and latency test</p>
      </div>

      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h2 className="text-xl font-semibold text-amber-400 mb-4">Test Engine</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-amber-400 mb-2">
              Server URL (leave blank for same-origin)
            </label>
            <input
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              disabled={isRunning}
              placeholder="e.g., https://waddleperf.example.com"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-200 placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-500"
              data-testid="server-url-input"
              aria-label="Speed test server URL"
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleStart}
              disabled={isRunning}
              className="px-4 py-2 bg-sky-500 text-slate-900 font-medium rounded-lg hover:bg-sky-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              data-testid="start-button"
              aria-label="Start speed test"
            >
              {isRunning ? 'Testing...' : 'Start Test'}
            </button>
            <button
              onClick={handleReset}
              disabled={isRunning}
              className="px-4 py-2 bg-slate-600 text-slate-200 font-medium rounded-lg hover:bg-slate-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              data-testid="reset-button"
              aria-label="Reset speed test"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-slate-300">Status</span>
          <span
            className={
              phase === 'error'
                ? 'text-red-400'
                : phase === 'complete'
                  ? 'text-green-400'
                  : isRunning
                    ? 'text-sky-400'
                    : 'text-slate-400'
            }
            data-testid="phase-label"
          >
            {phaseLabels[phase]}
          </span>
        </div>
        {error && (
          <p className="text-red-300 text-sm mt-2" data-testid="error-message">
            {error}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Latency" value={ping ? ping.latencyMs.toFixed(1) : '--'} unit="ms" />
        <MetricCard label="Jitter" value={ping ? ping.jitterMs.toFixed(1) : '--'} unit="ms" />
        <MetricCard
          label="Download"
          value={download ? download.mbps.toFixed(2) : '--'}
          unit="Mbps"
        />
        <MetricCard label="Upload" value={upload ? upload.mbps.toFixed(2) : '--'} unit="Mbps" />
      </div>

      {series.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-amber-400 mb-4">Realtime Throughput</h2>
          <Suspense fallback={<div className="w-full h-64 bg-slate-700 rounded animate-pulse" />}>
            <SpeedTestChart data={series} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
