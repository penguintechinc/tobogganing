import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  AutoPerfPolicy,
  listAutoPerfPolicies,
  createAutoPerfPolicy,
  deleteAutoPerfPolicy,
  getAutoPerfPolicyState,
} from '../../api/wpcOps';

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    T1: 'bg-blue-900 text-blue-200',
    T2: 'bg-yellow-900 text-yellow-200',
    T3: 'bg-red-900 text-red-200',
  };

  return (
    <span className={`px-2 py-1 rounded text-sm ${colors[tier] || 'bg-slate-700 text-slate-300'}`}>
      {tier}
    </span>
  );
}

function PolicyStatePanel({ policyId }: { policyId: string }) {
  const { data: state, isLoading } = useQuery({
    queryKey: ['autoperf', policyId, 'state'],
    queryFn: () => getAutoPerfPolicyState(policyId),
    staleTime: 2 * 60 * 1000,
  });

  if (isLoading) return <div className="text-slate-400 text-sm">Loading state...</div>;
  if (!state) return <div className="text-slate-400 text-sm">No state available</div>;

  return (
    <div className="bg-slate-800 rounded p-3 space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-slate-400">Tier:</span>
        <TierBadge tier={state.current_tier} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-400">Clean Cycles:</span>
        <span className="text-amber-300 font-semibold">{state.clean_cycles}</span>
      </div>
      {state.escalated_at && (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Escalated:</span>
          <span className="text-slate-300">{new Date(state.escalated_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}

export function AutoPerfPage() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [expandedPolicy, setExpandedPolicy] = useState<string | null>(null);

  const {
    data: policies = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['autoperf', 'policies'],
    queryFn: listAutoPerfPolicies,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createAutoPerfPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autoperf', 'policies'] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAutoPerfPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autoperf', 'policies'] });
    },
  });

  const basePolicyColumns: ColumnConfig<AutoPerfPolicy>[] = [
    { key: 'name', label: 'Policy Name', sortable: true },
    { key: 'device_id', label: 'Device', sortable: true },
    { key: 'target', label: 'Target', sortable: true },
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

  const columns: ColumnConfig<AutoPerfPolicy>[] = canWrite()
    ? [
        ...basePolicyColumns,
        {
          key: 'id' as keyof AutoPerfPolicy,
          label: 'Actions',
          render: (id) => (
            <div className="flex gap-2">
              <button
                onClick={() =>
                  setExpandedPolicy(expandedPolicy === (id as string) ? null : (id as string))
                }
                className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
              >
                {expandedPolicy === id ? 'Hide' : 'State'}
              </button>
              <button
                onClick={() => deleteMutation.mutate(id as string)}
                disabled={deleteMutation.isPending}
                className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
              >
                Delete
              </button>
            </div>
          ),
        },
      ]
    : [
        ...basePolicyColumns,
        {
          key: 'id' as keyof AutoPerfPolicy,
          label: 'State',
          render: (id) => (
            <button
              onClick={() =>
                setExpandedPolicy(expandedPolicy === (id as string) ? null : (id as string))
              }
              className="px-2 py-1 bg-sky-900 hover:bg-sky-800 text-sky-200 rounded text-sm"
            >
              {expandedPolicy === id ? 'Hide' : 'View'}
            </button>
          ),
        },
      ];

  console.log('[AutoPerfPage] Render { policies:', policies.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">AutoPerf</h1>
        <p className="text-slate-400 text-sm mt-1">Manage tiered monitoring policies</p>
      </div>

      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded"
        >
          {showForm ? 'Cancel' : 'Create Policy'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            createMutation.mutate({
              name: formData.get('name') as string,
              device_id: formData.get('device_id') as string,
              target: formData.get('target') as string,
              t1_interval_seconds: parseInt(formData.get('t1_interval_seconds') as string),
              t2_interval_seconds: parseInt(formData.get('t2_interval_seconds') as string),
              t3_interval_seconds: parseInt(formData.get('t3_interval_seconds') as string),
              deescalate_after_clean: parseInt(formData.get('deescalate_after_clean') as string),
            });
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
        >
          <input
            name="name"
            placeholder="Policy name"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="device_id"
            placeholder="Device ID"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="target"
            placeholder="Target IP/hostname"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="t1_interval_seconds"
            type="number"
            placeholder="T1 interval (seconds, default 300)"
            defaultValue="300"
            min="30"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="t2_interval_seconds"
            type="number"
            placeholder="T2 interval (seconds, default 120)"
            defaultValue="120"
            min="30"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="t3_interval_seconds"
            type="number"
            placeholder="T3 interval (seconds, default 60)"
            defaultValue="60"
            min="30"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="deescalate_after_clean"
            type="number"
            placeholder="De-escalate after clean cycles (default 3)"
            defaultValue="3"
            min="1"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded"
          >
            Create
          </button>
        </form>
      )}

      <DataTable
        columns={columns}
        data={policies}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />

      {expandedPolicy && (
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-amber-400 font-semibold mb-3">
            State for {policies.find((p) => p.id === expandedPolicy)?.name}
          </h3>
          <PolicyStatePanel policyId={expandedPolicy} />
        </div>
      )}
    </div>
  );
}
