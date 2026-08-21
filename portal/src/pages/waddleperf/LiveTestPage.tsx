import React, { useState, Suspense } from 'react';
import { useLiveTest } from '../../hooks/useLiveTest';
import { useRole } from '../../hooks/useRole';
import { useLazyLoadChart } from '../../hooks/useLazyLoadChart';

interface FormData {
  device_id: string;
  test_type: string;
  target: string;
}

export function LiveTestPage() {
  const { canWrite } = useRole();
  const { status, events, series, start, reset } = useLiveTest();
  const [formData, setFormData] = useState<FormData>({
    device_id: '',
    test_type: 'http',
    target: '',
  });
  const [isRunning, setIsRunning] = useState(false);
  const ChartComponent = useLazyLoadChart();

  const handleFormChange = (field: keyof FormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleStartTest = async () => {
    if (!formData.device_id || !formData.target) {
      console.warn('[LiveTestPage] Missing required fields');
      return;
    }

    console.log('[LiveTestPage] Starting test', formData);
    setIsRunning(true);

    try {
      await start(formData);
    } catch (err) {
      console.error('[LiveTestPage] Failed to start test', err);
      setIsRunning(false);
    }
  };

  const handleReset = () => {
    console.log('[LiveTestPage] Resetting');
    reset();
    setIsRunning(false);
    setFormData({ device_id: '', test_type: 'http', target: '' });
  };

  const statusColors = {
    connecting: 'text-yellow-400',
    open: 'text-green-400',
    closed: 'text-slate-400',
    error: 'text-red-400',
  };

  const statusLabels = {
    connecting: 'Connecting...',
    open: 'Connected',
    closed: 'Disconnected',
    error: 'Error',
  };

  const chartData = series.map((point) => ({
    timestamp: new Date(point.timestamp).toLocaleTimeString(),
    latency: point.latency || 0,
    throughput: point.throughput || 0,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-amber-400 mb-2">Live Test</h1>
        <p className="text-slate-400">Real-time network performance testing</p>
      </div>

      {/* Connection Status */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-slate-300">Connection Status</span>
          <div className={`flex items-center gap-2 ${statusColors[status]}`}>
            <div className="w-3 h-3 rounded-full bg-current animate-pulse" />
            <span>{statusLabels[status]}</span>
          </div>
        </div>
      </div>

      {/* Test Form */}
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h2 className="text-xl font-semibold text-amber-400 mb-4">Run Test</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-amber-400 mb-2">Device ID *</label>
            <input
              type="text"
              value={formData.device_id}
              onChange={(e) => handleFormChange('device_id', e.target.value)}
              disabled={!canWrite() || isRunning}
              placeholder="e.g., device-uuid-123"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-200 placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-500"
              data-testid="device-id-input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-amber-400 mb-2">Test Type *</label>
            <select
              value={formData.test_type}
              onChange={(e) => handleFormChange('test_type', e.target.value)}
              disabled={!canWrite() || isRunning}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-500"
              data-testid="test-type-select"
            >
              <option value="http">HTTP</option>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
              <option value="icmp">ICMP</option>
              <option value="http_trace">HTTP Trace</option>
              <option value="tcp_trace">TCP Trace</option>
              <option value="traceroute">Traceroute</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-amber-400 mb-2">Target *</label>
            <input
              type="text"
              value={formData.target}
              onChange={(e) => handleFormChange('target', e.target.value)}
              disabled={!canWrite() || isRunning}
              placeholder="e.g., example.com or 8.8.8.8"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-200 placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-500"
              data-testid="target-input"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <button
              onClick={handleStartTest}
              disabled={!canWrite() || isRunning || !formData.device_id || !formData.target}
              className="px-4 py-2 bg-sky-500 text-slate-900 font-medium rounded-lg hover:bg-sky-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              data-testid="start-button"
            >
              {isRunning ? 'Test Running...' : 'Start Test'}
            </button>

            <button
              onClick={handleReset}
              disabled={isRunning}
              className="px-4 py-2 bg-slate-600 text-slate-200 font-medium rounded-lg hover:bg-slate-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              data-testid="reset-button"
            >
              Reset
            </button>
          </div>

          {!canWrite() && (
            <div className="text-sm text-amber-400 italic">
              Read-only mode: you cannot run tests
            </div>
          )}
        </div>
      </div>

      {/* Chart */}
      {ChartComponent && chartData.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-amber-400 mb-4">Performance Metrics</h2>
          <Suspense fallback={<div className="w-full h-64 bg-slate-700 rounded animate-pulse" />}>
            <div className="w-full h-64">
              <ChartComponent data={chartData} />
            </div>
          </Suspense>
        </div>
      )}

      {chartData.length === 0 && series.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center text-slate-400">
          Waiting for data...
        </div>
      )}

      {/* Events Log */}
      {events.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-amber-400 mb-4">
            Recent Events ({events.length})
          </h2>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {events.slice(-10).map((event, idx) => (
              <div
                key={idx}
                className={`text-sm px-3 py-2 rounded ${
                  event.event === 'error'
                    ? 'bg-red-900/30 text-red-300'
                    : event.event === 'test_complete'
                      ? 'bg-green-900/30 text-green-300'
                      : 'bg-blue-900/30 text-blue-300'
                }`}
                data-testid={`event-${idx}`}
              >
                <span className="font-semibold">{event.event}</span>
                {event.data && typeof event.data === 'object' && 'message' in event.data && (
                  <span className="ml-2 text-slate-300">
                    {String((event.data as Record<string, unknown>).message)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
