import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import { listClusters, type Cluster } from '../../api/sase';

export function ClustersPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['sase', 'clusters'],
    queryFn: listClusters,
    staleTime: 5 * 60 * 1000,
  });

  console.log('[ClustersPage] Render { count:', data.length, '}');

  const columns: ColumnConfig<Cluster>[] = [
    {
      key: 'name',
      label: 'Name',
      sortable: true,
      render: (_, row) => (
        <button
          onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
          className="flex items-center gap-2 text-amber-400 hover:text-amber-300"
          aria-label={`Toggle details for cluster ${row.name}`}
        >
          {expandedId === row.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          {row.name}
        </button>
      ),
    },
    {
      key: 'region',
      label: 'Region',
      sortable: true,
    },
    {
      key: 'datacenter',
      label: 'Datacenter',
      sortable: true,
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
      key: 'client_count',
      label: 'Clients',
      sortable: true,
    },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-amber-400">Clusters</h1>
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
      {expandedId && (
        <div className="bg-slate-800 rounded-lg p-4">
          <ClusterDetail
            cluster={data.find((c) => c.id === expandedId)}
            onClose={() => setExpandedId(null)}
          />
        </div>
      )}
    </div>
  );
}

interface ClusterDetailProps {
  cluster: Cluster | undefined;
  onClose: () => void;
}

function ClusterDetail({ cluster, onClose }: ClusterDetailProps) {
  if (!cluster) {
    return null;
  }

  console.log('[ClusterDetail] Render { id:', cluster.id, '}');

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-amber-400">{cluster.name}</h2>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200"
          aria-label="Close details"
        >
          ✕
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-slate-400">ID</p>
          <p className="text-amber-100 font-mono text-xs">{cluster.id}</p>
        </div>
        <div>
          <p className="text-slate-400">Region</p>
          <p className="text-amber-100">{cluster.region}</p>
        </div>
        <div>
          <p className="text-slate-400">Datacenter</p>
          <p className="text-amber-100">{cluster.datacenter}</p>
        </div>
        <div>
          <p className="text-slate-400">Clients</p>
          <p className="text-amber-100">{cluster.client_count}</p>
        </div>
        <div>
          <p className="text-slate-400">Status</p>
          <p className={cluster.status === 'active' ? 'text-green-400' : 'text-yellow-400'}>
            {cluster.status}
          </p>
        </div>
      </div>
    </div>
  );
}
