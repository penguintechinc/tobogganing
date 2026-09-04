import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  Endpoint,
  listEndpoints,
  createEndpoint,
  deleteEndpoint,
  CreateEndpointPayload,
} from '../../api/c2c';

function HealthBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`px-2 py-1 rounded text-sm ${
        enabled ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'
      }`}
    >
      {enabled ? 'Healthy' : 'Offline'}
    </span>
  );
}

function EndpointsPage() {
  const { canWrite: canWriteFn } = useRole();
  const canWrite = canWriteFn();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<CreateEndpointPayload>({
    region: '',
    name: '',
    engine_url: '',
    target: '',
  });

  const queryClient = useQueryClient();

  const {
    data: endpoints = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['c2c', 'endpoints'],
    queryFn: listEndpoints,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'endpoints'] });
      setShowForm(false);
      setFormData({ region: '', name: '', engine_url: '', target: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'endpoints'] });
    },
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.region && formData.name && formData.engine_url && formData.target) {
      createMutation.mutate(formData);
    }
  };

  const columns: ColumnConfig<Endpoint>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'region', label: 'Region', sortable: true },
    { key: 'visibility', label: 'Visibility', sortable: false },
    { key: 'provider', label: 'Provider', sortable: false },
    {
      key: 'enabled',
      label: 'Status',
      sortable: false,
      render: (enabled) => <HealthBadge enabled={Boolean(enabled)} />,
    },
    ...(canWrite
      ? [
          {
            key: 'id',
            label: 'Actions',
            sortable: false,
            render: (id) => (
              <button
                onClick={() => deleteMutation.mutate(String(id))}
                className="text-red-400 hover:text-red-300"
                aria-label={`Delete endpoint ${id}`}
              >
                Delete
              </button>
            ),
          } as ColumnConfig<Endpoint>,
        ]
      : []),
  ];

  console.log('[EndpointsPage] Render { endpoints:', endpoints.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">C2C Nodes</h1>
        <p className="text-slate-400 text-sm mt-1">Manage cluster-to-cluster test endpoints</p>
      </div>

      {canWrite && (
        <div className="flex gap-2">
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-sky-600 text-white rounded hover:bg-sky-700"
          >
            {showForm ? 'Cancel' : 'Create Endpoint'}
          </button>
        </div>
      )}

      {showForm && canWrite && (
        <form
          onSubmit={handleCreate}
          className="bg-slate-800 p-4 rounded space-y-3 border border-slate-700"
        >
          <div>
            <label className="block text-amber-400 text-sm mb-1">Region *</label>
            <input
              type="text"
              value={formData.region}
              onChange={(e) => setFormData({ ...formData, region: e.target.value })}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="e.g., us-west-2"
              required
            />
          </div>
          <div>
            <label className="block text-amber-400 text-sm mb-1">Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="e.g., primary-node"
              required
            />
          </div>
          <div>
            <label className="block text-amber-400 text-sm mb-1">Engine URL *</label>
            <input
              type="url"
              value={formData.engine_url}
              onChange={(e) => setFormData({ ...formData, engine_url: e.target.value })}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="http://engine.local:8080"
              required
            />
          </div>
          <div>
            <label className="block text-amber-400 text-sm mb-1">Target *</label>
            <input
              type="text"
              value={formData.target}
              onChange={(e) => setFormData({ ...formData, target: e.target.value })}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="node.example.com"
              required
            />
          </div>
          <div>
            <label className="block text-amber-400 text-sm mb-1">API Key (optional)</label>
            <input
              type="password"
              value={formData.api_key || ''}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="auto-generated if empty"
            />
          </div>
          <button
            type="submit"
            className="w-full px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </button>
        </form>
      )}

      <DataTable
        columns={columns}
        data={endpoints}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}

export { EndpointsPage };
