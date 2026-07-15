import React, { Suspense, lazy } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStatsSummary, getStatsTrends } from '../../api/waddleperf';

const TrendsChart = lazy(() => import('../../components/TrendsChart'));

function StatCard({
  label,
  value,
  unit = '',
}: {
  label: string;
  value: number;
  unit?: string;
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded p-4">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className="text-2xl font-bold text-amber-400 mt-2">
        {value.toLocaleString()}
        {unit && <span className="text-sm ml-1">{unit}</span>}
      </p>
    </div>
  );
}

export function StatsPage() {
  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['waddleperf', 'stats', 'summary'],
    queryFn: getStatsSummary,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: trends = [],
    isLoading: trendsLoading,
    error: trendsError,
    refetch: refetchTrends,
  } = useQuery({
    queryKey: ['waddleperf', 'stats', 'trends'],
    queryFn: getStatsTrends,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading = summaryLoading || trendsLoading;
  const error = summaryError || trendsError;

  console.log('[StatsPage] Render { summary:', !!summary, 'trends:', trends.length, '}');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Statistics</h1>
        <p className="text-slate-400 text-sm mt-1">
          Overview of WaddlePerf cluster performance metrics
        </p>
      </div>

      {error && (
        <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded">
          <p className="font-semibold">Error loading statistics</p>
          <p className="text-sm">{error.message}</p>
          <button
            onClick={() => {
              refetchSummary();
              refetchTrends();
            }}
            className="mt-2 px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-sm"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-24 bg-slate-700 rounded animate-pulse"
            />
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Tests" value={summary.total_tests} />
          <StatCard label="Total Devices" value={summary.total_devices} />
          <StatCard
            label="Success Rate"
            value={Math.round(summary.success_rate * 100)}
            unit="%"
          />
          <StatCard
            label="Avg Latency"
            value={Math.round(summary.avg_latency_ms)}
            unit="ms"
          />
        </div>
      ) : null}

      <div className="bg-slate-800 border border-slate-700 rounded p-4">
        <h2 className="text-lg font-semibold text-amber-400 mb-4">
          Trends Over Time
        </h2>
        {trendsLoading ? (
          <div className="h-64 bg-slate-700 rounded animate-pulse" />
        ) : trendsError ? (
          <div className="text-red-300 text-sm">Failed to load trends</div>
        ) : (
          <Suspense fallback={<div className="h-64 bg-slate-700 rounded" />}>
            <TrendsChart data={trends} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
