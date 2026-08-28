import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  AutoCheckIn,
  listAutoCheckIns,
  createAutoCheckIn,
  deleteAutoCheckIn,
  getAutoCheckInState,
} from '../../api/wpcOps';

/** Colored badge showing a check-in's cascade tier (1-3). */
function TierBadge({ tier }: { tier: number }) {
  const colors: Record<number, string> = {
    1: 'bg-blue-900 text-blue-200',
    2: 'bg-yellow-900 text-yellow-200',
    3: 'bg-red-900 text-red-200',
  };
  return (
    <span className={`px-2 py-1 rounded text-sm ${colors[tier] || 'bg-slate-700 text-slate-300'}`}>
      T{tier}
    </span>
  );
}

/** Fetches and renders the cascade state (last breach, mean/stddev, last run) for one check-in. */
function CheckinStatePanel({ checkinId }: { checkinId: string }) {
  const { data: state, isLoading } = useQuery({
    queryKey: ['auto-checkins', checkinId, 'state'],
    queryFn: () => getAutoCheckInState(checkinId),
    staleTime: 60 * 1000,
  });

  if (isLoading) return <div className="text-slate-400 text-sm">Loading state...</div>;
  if (!state) return <div className="text-slate-400 text-sm">No state available</div>;

  return (
    <div className="bg-slate-800 rounded p-3 space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-slate-400">Last Breached:</span>
        <span className={state.last_breached ? 'text-red-400' : 'text-green-400'}>
          {state.last_breached ? 'Yes' : 'No'}
        </span>
      </div>
      {state.last_mean_latency_ms !== null && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Mean Latency:</span>
          <span className="text-amber-300">{state.last_mean_latency_ms.toFixed(2)} ms</span>
        </div>
      )}
      {state.last_stddev_latency_ms !== null && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Std Dev:</span>
          <span className="text-amber-300">{state.last_stddev_latency_ms.toFixed(2)} ms</span>
        </div>
      )}
      {state.last_run_at && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Last Run:</span>
          <span className="text-slate-300">{new Date(state.last_run_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Admin page for tiered, jittered, std-dev-thresholded Auto Check-ins:
 * lists check-ins per tenant, supports create/delete (Admin/Maintainer only),
 * and exposes cascade state (last breach, mean/stddev latency) per check-in.
 */
export function AutoCheckInsPage() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [expandedCheckin, setExpandedCheckin] = useState<string | null>(null);

  const {
    data: checkins = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['auto-checkins'],
    queryFn: listAutoCheckIns,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createAutoCheckIn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-checkins'] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAutoCheckIn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-checkins'] });
    },
  });

  const baseColumns: ColumnConfig<AutoCheckIn>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'device_id', label: 'Source Device', sortable: true },
    { key: 'target', label: 'Target', sortable: true },
    {
      key: 'tier' as keyof AutoCheckIn,
      label: 'Tier',
      render: (tier) => <TierBadge tier={tier as number} />,
    },
    {
      key: 'enabled',
      label: 'Status',
      render: (enabled) => (
        <span className={enabled ? 'text-green-400' : 'text-slate-400'}>
          {enabled ? 'Active' : 'Inactive'}
        </span>
      ),
    },
  ];

  const columns: ColumnConfig<AutoCheckIn>[] = canWrite()
    ? [
        ...baseColumns,
        {
          key: 'id' as keyof AutoCheckIn,
          label: 'Actions',
          render: (id) => (
            <div className="flex gap-2">
              <button
                onClick={() =>
                  setExpandedCheckin(expandedCheckin === (id as string) ? null : (id as string))
                }
                className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
                aria-label={`Toggle state for check-in ${id as string}`}
              >
                {expandedCheckin === id ? 'Hide' : 'State'}
              </button>
              <button
                onClick={() => deleteMutation.mutate(id as string)}
                disabled={deleteMutation.isPending}
                className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
                aria-label={`Delete check-in ${id as string}`}
              >
                Delete
              </button>
            </div>
          ),
        },
      ]
    : [
        ...baseColumns,
        {
          key: 'id' as keyof AutoCheckIn,
          label: 'State',
          render: (id) => (
            <button
              onClick={() =>
                setExpandedCheckin(expandedCheckin === (id as string) ? null : (id as string))
              }
              className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
              aria-label={`Toggle state for check-in ${id as string}`}
            >
              {expandedCheckin === id ? 'Hide' : 'State'}
            </button>
          ),
        },
      ];

  console.log('[AutoCheckInsPage] Render { checkins:', checkins.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Auto Check-ins</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configure tiered, jittered, std-dev-thresholded probe check-ins
        </p>
      </div>

      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded focus:ring-2 focus:ring-sky-500"
        >
          {showForm ? 'Cancel' : 'Create Check-in'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            const thresholdMax = formData.get('threshold_stddev_max') as string;
            createMutation.mutate({
              name: formData.get('name') as string,
              device_id: formData.get('device_id') as string,
              target_kind: formData.get('target_kind') as 'ours' | 'external',
              target: formData.get('target') as string,
              interval_minutes: parseInt(formData.get('interval_minutes') as string, 10),
              jitter_pct: parseInt(formData.get('jitter_pct') as string, 10),
              samples_per_run: parseInt(formData.get('samples_per_run') as string, 10),
              tier: parseInt(formData.get('tier') as string, 10),
              ...(thresholdMax ? { threshold_stddev_max: parseFloat(thresholdMax) } : {}),
            });
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
          aria-label="Create Auto Check-in"
        >
          <input
            name="name"
            placeholder="Check-in name"
            required
            aria-label="Check-in name"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <input
            name="device_id"
            placeholder="Source device ID"
            required
            aria-label="Source device ID"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <select
            name="target_kind"
            defaultValue="external"
            aria-label="Target kind"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          >
            <option value="ours">Ours (internal service)</option>
            <option value="external">External (URL/host:port)</option>
          </select>
          <input
            name="target"
            placeholder="Target (URL/host:port)"
            required
            aria-label="Target"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <input
            name="interval_minutes"
            type="number"
            placeholder="Interval (minutes, 1-60, default 5)"
            defaultValue="5"
            min="1"
            max="60"
            aria-label="Interval minutes"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <input
            name="jitter_pct"
            type="number"
            placeholder="Jitter (%, 0-10, default 0)"
            defaultValue="0"
            min="0"
            max="10"
            aria-label="Jitter percent"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <input
            name="samples_per_run"
            type="number"
            placeholder="Samples per run (1-5, default 1)"
            defaultValue="1"
            min="1"
            max="5"
            aria-label="Samples per run"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <input
            name="threshold_stddev_max"
            type="number"
            step="0.1"
            placeholder="Max acceptable std-dev (ms, optional)"
            aria-label="Max acceptable standard deviation"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          />
          <select
            name="tier"
            defaultValue="1"
            aria-label="Cascade tier"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded focus:ring-2 focus:ring-sky-500"
          >
            <option value="1">Tier 1 (always runs)</option>
            <option value="2">Tier 2 (runs when its Tier-1 parent breaches)</option>
            <option value="3">Tier 3 (runs when its Tier-2 parent breaches)</option>
          </select>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded focus:ring-2 focus:ring-sky-500"
          >
            Create
          </button>
        </form>
      )}

      <DataTable
        columns={columns}
        data={checkins}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />

      {expandedCheckin && (
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-amber-400 font-semibold mb-3">
            State for {checkins.find((c) => c.id === expandedCheckin)?.name}
          </h3>
          <CheckinStatePanel checkinId={expandedCheckin} />
        </div>
      )}
    </div>
  );
}
