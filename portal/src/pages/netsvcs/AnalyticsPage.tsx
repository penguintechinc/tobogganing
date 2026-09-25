import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import TrendsChart from '../../components/TrendsChart';
import {
  getAnalyticsPerformance,
  getAnalyticsQueries,
  getAnalyticsServers,
  getAnalyticsSummary,
  type ServerSummaryEntry,
} from '../../api/netsvcs';

/**
 * AnalyticsPage — netsvcs DNS dashboard: tenant summary counts, query
 * volume trend, response-time performance, and a per-server breakdown.
 */
export function AnalyticsPage() {
  const { data: summary = [] } = useQuery({
    queryKey: ['netsvcs', 'analytics', 'summary'],
    queryFn: getAnalyticsSummary,
    staleTime: 60 * 1000,
  });

  const {
    data: queries,
    isLoading: queriesLoading,
    error: queriesError,
    refetch: refetchQueries,
  } = useQuery({
    queryKey: ['netsvcs', 'analytics', 'queries'],
    queryFn: () => getAnalyticsQueries(),
    staleTime: 60 * 1000,
  });

  const { data: performance = [] } = useQuery({
    queryKey: ['netsvcs', 'analytics', 'performance'],
    queryFn: () => getAnalyticsPerformance(),
    staleTime: 60 * 1000,
  });

  const {
    data: servers = [],
    isLoading: serversLoading,
    error: serversError,
    refetch: refetchServers,
  } = useQuery({
    queryKey: ['netsvcs', 'analytics', 'servers'],
    queryFn: () => getAnalyticsServers(),
    staleTime: 60 * 1000,
  });

  console.log(
    '[AnalyticsPage] Render { summaryCount:',
    summary.length,
    'serverCount:',
    servers.length,
    '}'
  );

  const summaryByKey = Object.fromEntries(summary.map((m) => [m.key, m.value]));
  const trendData = (queries?.timeline ?? []).map((t) => ({
    timestamp: t.timestamp,
    value: t.queries,
  }));

  const serverColumns: ColumnConfig<ServerSummaryEntry & { id: string }>[] = [
    { key: 'server_name', label: 'Server', sortable: true },
    { key: 'queries', label: 'Queries', sortable: true },
    { key: 'cache_hits', label: 'Cache Hits', sortable: true },
    { key: 'errors', label: 'Errors', sortable: true },
    {
      key: 'avg_response_ms',
      label: 'Avg Response (ms)',
      sortable: true,
      render: (v) => Number(v).toFixed(2),
    },
  ];

  const serverRows = servers.map((s) => ({ ...s, id: s.server_id }));

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-amber-400">Analytics</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard label="Zones" value={summaryByKey.zones ?? 0} />
        <SummaryCard label="Records" value={summaryByKey.records ?? 0} />
        <SummaryCard label="Servers" value={summaryByKey.servers ?? 0} />
        <SummaryCard label="Queries (24h)" value={summaryByKey.queries_24h ?? 0} />
      </div>

      <div className="bg-slate-800 rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-amber-400">Query Volume</h2>
        {queriesLoading ? (
          <div className="h-64 bg-slate-700 rounded animate-pulse" />
        ) : queriesError ? (
          <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded">
            <p className="font-semibold">Error loading query analytics</p>
            <button
              onClick={() => refetchQueries()}
              className="mt-2 px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-sm"
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            <TrendsChart data={trendData} />
            {queries && (
              <div className="grid grid-cols-3 gap-4 text-sm text-slate-300">
                <p>
                  Total queries:{' '}
                  <span className="text-amber-100 font-semibold">{queries.total_queries}</span>
                </p>
                <p>
                  Cache hit rate:{' '}
                  <span className="text-amber-100 font-semibold">
                    {queries.cache_hit_rate.toFixed(1)}%
                  </span>
                </p>
                <p>
                  Errors:{' '}
                  <span className="text-amber-100 font-semibold">{queries.total_errors}</span>
                </p>
              </div>
            )}
          </>
        )}
      </div>

      <div className="bg-slate-800 rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-amber-400">Performance</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {performance.map((metric) => (
            <div key={metric.metric} className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">{metric.metric}</p>
              <p className="text-amber-100 text-lg font-semibold">{metric.value.toFixed(2)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-amber-400 mb-3">Per-Server Breakdown</h2>
        <DataTable
          columns={serverColumns}
          data={serverRows}
          isLoading={serversLoading}
          error={serversError}
          onRetry={() => refetchServers()}
          pageSize={25}
        />
      </div>
    </div>
  );
}

interface SummaryCardProps {
  label: string;
  value: number;
}

function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className="text-2xl font-bold text-amber-400">{value}</p>
    </div>
  );
}
