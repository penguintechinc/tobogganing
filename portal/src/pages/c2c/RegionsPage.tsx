import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { Region, VisibleNode, listRegions, listVisibleNodes } from '../../api/c2c';

function RegionCard({ region }: { region: Region }) {
  const healthPercent =
    region.node_count > 0
      ? Math.round((region.healthy_count / region.node_count) * 100)
      : 0;

  return (
    <div className="bg-slate-800 p-4 rounded border border-slate-700 space-y-2">
      <h3 className="text-amber-400 font-semibold text-lg">{region.region}</h3>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between text-slate-300">
          <span>Total Nodes:</span>
          <span className="text-amber-300 font-semibold">
            {region.node_count}
          </span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span>Healthy:</span>
          <span
            className={`font-semibold ${
              healthPercent >= 80 ? 'text-green-300' : 'text-amber-300'
            }`}
          >
            {region.healthy_count}/{region.node_count}
          </span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span>Health %:</span>
          <span
            className={`font-semibold ${
              healthPercent >= 80 ? 'text-green-300' : 'text-amber-300'
            }`}
          >
            {healthPercent}%
          </span>
        </div>
        {region.providers && region.providers.length > 0 && (
          <div className="text-slate-400 text-xs mt-2">
            <span>Providers: </span>
            {region.providers.join(', ')}
          </div>
        )}
      </div>
    </div>
  );
}

function RegionsPage() {
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  const {
    data: regions = [],
    isLoading: regionsLoading,
    error: regionsError,
  } = useQuery({
    queryKey: ['c2c', 'regions'],
    queryFn: listRegions,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: nodes = [],
    isLoading: nodesLoading,
    error: nodesError,
    refetch: refetchNodes,
  } = useQuery({
    queryKey: ['c2c', 'nodes', selectedRegion],
    queryFn: () => listVisibleNodes(selectedRegion || undefined),
    staleTime: 5 * 60 * 1000,
    enabled: !!selectedRegion,
  });

  const columns: ColumnConfig<VisibleNode>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'region', label: 'Region', sortable: true },
    {
      key: 'engine_url',
      label: 'Engine URL',
      sortable: false,
      render: (engineUrl) => (
        <span className="text-slate-400 text-sm">
          {engineUrl ? (engineUrl as string) : '(redacted)'}
        </span>
      ),
    },
    { key: 'target', label: 'Target', sortable: true },
    {
      key: 'enabled',
      label: 'Status',
      sortable: false,
      render: (enabled) => (
        <span
          className={`px-2 py-1 rounded text-sm ${
            enabled
              ? 'bg-green-900 text-green-200'
              : 'bg-red-900 text-red-200'
          }`}
        >
          {enabled ? 'Healthy' : 'Offline'}
        </span>
      ),
    },
  ];

  console.log('[RegionsPage] Render { regions:', regions.length, ', selectedRegion:', selectedRegion, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">C2C Regions</h1>
        <p className="text-slate-400 text-sm mt-1">
          Region health summary and node inventory
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {regionsLoading ? (
          <div className="text-slate-400">Loading regions...</div>
        ) : regionsError ? (
          <div className="text-red-400">Failed to load regions</div>
        ) : regions.length === 0 ? (
          <div className="text-slate-400">No regions configured</div>
        ) : (
          regions.map((region) => (
            <button
              key={region.region}
              onClick={() =>
                setSelectedRegion(
                  selectedRegion === region.region ? null : region.region
                )
              }
              className={`text-left transition-all ${
                selectedRegion === region.region
                  ? 'ring-2 ring-sky-500'
                  : 'hover:ring-1 hover:ring-slate-600'
              }`}
            >
              <RegionCard region={region} />
            </button>
          ))
        )}
      </div>

      {selectedRegion && (
        <div className="space-y-3 bg-slate-800 p-4 rounded border border-slate-700">
          <div className="flex justify-between items-center">
            <h3 className="text-amber-400 font-semibold text-lg">
              Nodes in {selectedRegion}
            </h3>
            <button
              onClick={() => setSelectedRegion(null)}
              className="text-slate-400 hover:text-slate-300 text-sm"
            >
              ✕
            </button>
          </div>

          <DataTable
            columns={columns}
            data={nodes}
            isLoading={nodesLoading}
            error={nodesError}
            onRetry={() => refetchNodes()}
          />
        </div>
      )}
    </div>
  );
}

export { RegionsPage };
