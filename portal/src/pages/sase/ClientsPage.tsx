import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import { listClients, type Client } from '../../api/sase';

export function ClientsPage() {
  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['sase', 'clients'],
    queryFn: listClients,
    staleTime: 5 * 60 * 1000,
  });

  console.log('[ClientsPage] Render { count:', data.length, '}');

  const columns: ColumnConfig<Client>[] = [
    {
      key: 'name',
      label: 'Name',
      sortable: true,
    },
    {
      key: 'type',
      label: 'Type',
      sortable: true,
      render: (type) => (
        <span className="px-2 py-1 rounded text-sm bg-slate-700 text-amber-100">{type}</span>
      ),
    },
    {
      key: 'cluster_id',
      label: 'Cluster',
      sortable: true,
      render: (clusterId) => (
        <span className="text-slate-300 font-mono text-xs">{String(clusterId).slice(0, 8)}</span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (status) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            status === 'active' ? 'bg-green-900 text-green-100' : 'bg-yellow-900 text-yellow-100'
          }`}
        >
          {status}
        </span>
      ),
    },
    {
      key: 'last_seen',
      label: 'Last Seen',
      sortable: true,
      render: (lastSeen) => (
        <span className="text-slate-400 text-sm">
          {new Date(String(lastSeen)).toLocaleString()}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-amber-400">Clients</h1>
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
    </div>
  );
}
