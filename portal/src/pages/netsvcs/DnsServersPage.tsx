import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import LiveChart from '../../components/LiveChart';
import {
  deleteDnsServer,
  getDnsServerMetrics,
  listDnsServers,
  type DnsServer,
} from '../../api/netsvcs';

const serversKey = ['netsvcs', 'dns-servers'] as const;

/**
 * DnsServersPage — fleet view of enrolled DNS resolver servers with a
 * per-server metrics detail panel (queries/response-time over time).
 */
export function DnsServersPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: serversKey,
    queryFn: listDnsServers,
    staleTime: 60 * 1000,
  });

  console.log('[DnsServersPage] Render { count:', data.length, '}');

  const { mutate: removeServer } = useMutation({
    mutationFn: deleteDnsServer,
    onSuccess: (_result, serverId) => {
      console.log('[DnsServersPage] DeleteServer success { serverId }', { serverId });
      queryClient.invalidateQueries({ queryKey: serversKey });
      if (expandedId === serverId) {
        setExpandedId(null);
      }
    },
    onError: (err) => {
      console.error('[DnsServersPage] DeleteServer error', { error: String(err) });
      alert('Failed to delete DNS server');
    },
  });

  const handleDelete = (server: DnsServer) => {
    if (confirm(`Delete DNS server "${server.name}" and its metrics history?`)) {
      console.log('[DnsServersPage] DeleteServer { serverId }', { serverId: server.id });
      removeServer(server.id);
    }
  };

  const columns: ColumnConfig<DnsServer>[] = [
    {
      key: 'name',
      label: 'Name',
      sortable: true,
      render: (_, row) => (
        <button
          onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
          className="flex items-center gap-2 text-amber-400 hover:text-amber-300"
          aria-label={`Toggle metrics for server ${row.name}`}
        >
          {expandedId === row.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          {row.name}
        </button>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (status) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            status === 'online' ? 'bg-green-900 text-green-100' : 'bg-yellow-900 text-yellow-100'
          }`}
        >
          {String(status)}
        </span>
      ),
    },
    { key: 'region', label: 'Region', sortable: true, render: (v) => String(v ?? '-') },
    { key: 'hostname', label: 'Hostname', sortable: true, render: (v) => String(v ?? '-') },
    { key: 'version', label: 'Version', sortable: true, render: (v) => String(v ?? '-') },
    {
      key: 'last_heartbeat',
      label: 'Last Heartbeat',
      sortable: true,
      render: (v) => (v ? new Date(String(v)).toLocaleString() : 'never'),
    },
    {
      key: 'id',
      label: 'Actions',
      sortable: false,
      render: (_, row) => (
        <button
          onClick={() => handleDelete(row)}
          className="text-red-400 hover:text-red-300 transition-colors"
          aria-label={`Delete server ${row.name}`}
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ];

  const expandedServer = data.find((s) => s.id === expandedId);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-amber-400">DNS Servers</h1>

      <div className="bg-slate-800 rounded-lg p-4">
        <DataTable
          columns={columns}
          data={data}
          isLoading={isLoading}
          error={error}
          onRetry={() => refetch()}
          pageSize={25}
        />
      </div>

      {expandedServer && (
        <div className="bg-slate-800 rounded-lg p-4">
          <ServerMetricsPanel server={expandedServer} onClose={() => setExpandedId(null)} />
        </div>
      )}
    </div>
  );
}

interface ServerMetricsPanelProps {
  server: DnsServer;
  onClose: () => void;
}

function ServerMetricsPanel({ server, onClose }: ServerMetricsPanelProps) {
  const { data: metrics = [], isLoading } = useQuery({
    queryKey: ['netsvcs', 'dns-server-metrics', server.id],
    queryFn: () => getDnsServerMetrics(server.id),
    staleTime: 30 * 1000,
  });

  console.log('[ServerMetricsPanel] Render { serverId:', server.id, 'points:', metrics.length, '}');

  const chartData = metrics.map((m) => ({
    timestamp: new Date(m.timestamp).toLocaleTimeString(),
    latency: m.avg_response_ms,
    throughput: m.queries_total,
  }));

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-amber-400">Metrics: {server.name}</h2>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200"
          aria-label="Close metrics"
        >
          ✕
        </button>
      </div>

      {isLoading ? (
        <div className="h-64 bg-slate-700 rounded animate-pulse" />
      ) : (
        <div className="h-64">
          <LiveChart data={chartData} />
        </div>
      )}
    </div>
  );
}
