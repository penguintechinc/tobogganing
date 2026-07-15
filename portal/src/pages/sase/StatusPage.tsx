import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, AlertCircle } from 'lucide-react';
import { getStatus } from '../../api/sase';

export function StatusPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['sase', 'status'],
    queryFn: getStatus,
    staleTime: 30000, // 30s for status
  });

  console.log('[StatusPage] Render { loading:', isLoading, '}');

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-amber-400">Status</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-700 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-amber-400">Status</h1>
        <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded">
          <p className="font-semibold">Error loading status</p>
          <p className="text-sm">{error instanceof Error ? error.message : 'Unknown error'}</p>
          <button
            onClick={() => refetch()}
            className="mt-2 px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-amber-400">Status</h1>
        <div className="text-center py-8 text-slate-400">No data available</div>
      </div>
    );
  }

  const isHealthy = data.status === 'healthy';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold text-amber-400">Status</h1>
        {isHealthy ? (
          <Activity className="w-6 h-6 text-green-400" />
        ) : (
          <AlertCircle className="w-6 h-6 text-red-400" />
        )}
      </div>

      <div className="bg-slate-800 rounded-lg p-4">
        <p className="text-slate-400 text-sm mb-2">Service Status</p>
        <p className={`text-3xl font-bold ${isHealthy ? 'text-green-400' : 'text-red-400'}`}>
          {data.status.toUpperCase()}
        </p>
        <p className="text-slate-500 text-xs mt-2">{data.service}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatusCard title="Clusters" active={data.clusters.active} total={data.clusters.total} />
        <StatusCard title="Clients" active={data.clients.active} total={data.clients.total} />
      </div>

      <div className="bg-slate-800 rounded-lg p-3 text-xs text-slate-400">
        <p>Last updated: {new Date(data.meta.timestamp).toLocaleString()}</p>
      </div>
    </div>
  );
}

interface StatusCardProps {
  title: string;
  active: number;
  total: number;
}

function StatusCard({ title, active, total }: StatusCardProps) {
  const percentage = total > 0 ? Math.round((active / total) * 100) : 0;

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <p className="text-slate-400 text-sm mb-3">{title}</p>
      <div className="space-y-2">
        <div className="flex justify-between">
          <span className="text-amber-100">Active</span>
          <span className="text-green-400 font-semibold">{active}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-amber-100">Total</span>
          <span className="text-amber-100 font-semibold">{total}</span>
        </div>
        <div className="mt-3">
          <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
            <div
              className="bg-green-500 h-full transition-all"
              style={{ width: `${percentage}%` }}
            />
          </div>
          <p className="text-slate-500 text-xs mt-1">{percentage}% active</p>
        </div>
      </div>
    </div>
  );
}
