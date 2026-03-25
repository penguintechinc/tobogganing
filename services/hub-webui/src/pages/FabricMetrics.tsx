import { useQuery } from '@tanstack/react-query';
import { Activity, Gauge, Wifi, AlertTriangle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { fetchPerfSummary, fetchPerfMetrics } from '../lib/api/perf';
import type { PerfSummaryPair, PerfMetric } from '../lib/api/perf';

function StatCard({
  icon: Icon,
  label,
  value,
  alert,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-4">
      <div className="flex items-center gap-2">
        <Icon
          className={clsx(
            'h-5 w-5',
            alert ? 'text-red-400' : 'text-accent',
          )}
        />
        <span className="text-sm text-text-secondary">{label}</span>
      </div>
      <p
        className={clsx(
          'mt-2 text-2xl font-bold',
          alert ? 'text-red-400' : 'text-text-gold',
        )}
      >
        {value}
      </p>
    </div>
  );
}

export default function FabricMetrics() {
  const summaryQuery = useQuery({
    queryKey: ['perf-summary'],
    queryFn: fetchPerfSummary,
    refetchInterval: 30000,
  });

  const metricsQuery = useQuery({
    queryKey: ['perf-metrics'],
    queryFn: () => fetchPerfMetrics({ limit: 50 }),
    refetchInterval: 30000,
  });

  const pairs = summaryQuery.data?.data?.pairs ?? [];
  const metrics = metricsQuery.data?.data?.metrics ?? [];

  // Calculate summary stats
  const avgLatency =
    pairs.length > 0
      ? pairs.reduce((sum, p) => {
          const protos = Object.values(p.protocols);
          const lat =
            protos.reduce((s, pr) => s + (pr.latest_latency_ms ?? 0), 0) /
            (protos.length || 1);
          return sum + lat;
        }, 0) / pairs.length
      : 0;

  const maxLoss = pairs.reduce((max, p) => {
    const protos = Object.values(p.protocols);
    const loss = Math.max(...protos.map((pr) => pr.latest_packet_loss_pct ?? 0));
    return Math.max(max, loss);
  }, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Fabric Metrics</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Cluster-to-cluster and client-to-cluster performance monitoring
          </p>
        </div>
        <button
          onClick={() => {
            summaryQuery.refetch();
            metricsQuery.refetch();
          }}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Wifi} label="Monitored Pairs" value={String(pairs.length)} />
        <StatCard
          icon={Gauge}
          label="Avg Latency"
          value={`${avgLatency.toFixed(1)} ms`}
        />
        <StatCard
          icon={AlertTriangle}
          label="Max Packet Loss"
          value={`${maxLoss.toFixed(1)}%`}
          alert={maxLoss > 1}
        />
      </div>

      {/* Latency Matrix */}
      <div className="rounded-lg border border-border bg-bg-secondary">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold text-text-primary">
            Latency Matrix
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-secondary">
                <th className="px-4 py-3">Source → Target</th>
                <th className="px-4 py-3">HTTP</th>
                <th className="px-4 py-3">TCP</th>
                <th className="px-4 py-3">ICMP</th>
                <th className="px-4 py-3">Packet Loss</th>
                <th className="px-4 py-3">Last Measured</th>
              </tr>
            </thead>
            <tbody>
              {pairs.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-text-muted"
                  >
                    No fabric metrics available. Enable performance monitoring in
                    hub-router config.
                  </td>
                </tr>
              ) : (
                pairs.map((pair, i) => (
                  <tr
                    key={i}
                    className="border-b border-border last:border-0 hover:bg-bg-tertiary"
                  >
                    <td className="px-4 py-3 font-medium text-text-primary">
                      {pair.source_id} → {pair.target_id}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {pair.protocols.http?.latest_latency_ms?.toFixed(1) ??
                        '—'}{' '}
                      ms
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {pair.protocols.tcp?.latest_latency_ms?.toFixed(1) ?? '—'}{' '}
                      ms
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {pair.protocols.icmp?.latest_latency_ms?.toFixed(1) ??
                        '—'}{' '}
                      ms
                    </td>
                    <td
                      className={clsx(
                        'px-4 py-3',
                        (pair.protocols.icmp?.latest_packet_loss_pct ?? 0) > 1
                          ? 'text-red-400'
                          : 'text-text-secondary',
                      )}
                    >
                      {pair.protocols.icmp?.latest_packet_loss_pct?.toFixed(1) ??
                        '0.0'}
                      %
                    </td>
                    <td className="px-4 py-3 text-text-muted">
                      {Object.values(pair.protocols)[0]?.last_measured
                        ? new Date(
                            Object.values(pair.protocols)[0].last_measured,
                          ).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Metrics */}
      <div className="rounded-lg border border-border bg-bg-secondary">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold text-text-primary">
            Recent Measurements
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-secondary">
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Protocol</th>
                <th className="px-4 py-3">Latency</th>
                <th className="px-4 py-3">Jitter</th>
                <th className="px-4 py-3">Loss</th>
              </tr>
            </thead>
            <tbody>
              {metrics.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-8 text-center text-text-muted"
                  >
                    No recent measurements.
                  </td>
                </tr>
              ) : (
                metrics.map((m, i) => (
                  <tr
                    key={i}
                    className="border-b border-border last:border-0 hover:bg-bg-tertiary"
                  >
                    <td className="px-4 py-3 text-text-muted">
                      {m.timestamp
                        ? new Date(m.timestamp).toLocaleString()
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-text-primary">
                      {m.source_id}
                    </td>
                    <td className="px-4 py-3 text-text-primary">
                      {m.target_id}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs font-medium text-text-secondary uppercase">
                        {m.protocol}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {m.latency_ms?.toFixed(1)} ms
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {m.jitter_ms != null ? `${m.jitter_ms.toFixed(1)} ms` : '—'}
                    </td>
                    <td
                      className={clsx(
                        'px-4 py-3',
                        (m.packet_loss_pct ?? 0) > 1
                          ? 'text-red-400'
                          : 'text-text-secondary',
                      )}
                    >
                      {m.packet_loss_pct != null
                        ? `${m.packet_loss_pct.toFixed(1)}%`
                        : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
