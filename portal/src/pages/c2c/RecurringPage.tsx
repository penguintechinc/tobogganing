import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  RecurringJob,
  listRecurringJobs,
  createRecurringJob,
  deleteRecurringJob,
  updateRecurringJob,
  CreateRecurringPayload,
} from '../../api/c2c';

function RecurringPage() {
  const { canWrite: canWriteFn } = useRole();
  const canWrite = canWriteFn();
  const [showForm, setShowForm] = useState(false);
  const [jobType, setJobType] = useState<'matrix_run' | 'node_health'>('matrix_run');
  const [intervalSeconds, setIntervalSeconds] = useState<number>(300);

  const queryClient = useQueryClient();

  const {
    data: jobs = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['c2c', 'recurring'],
    queryFn: listRecurringJobs,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateRecurringPayload) => createRecurringJob(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'recurring'] });
      setShowForm(false);
      setJobType('matrix_run');
      setIntervalSeconds(300);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteRecurringJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'recurring'] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ jobId, enabled }: { jobId: string; enabled: boolean }) =>
      updateRecurringJob(jobId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'recurring'] });
    },
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (intervalSeconds >= 30) {
      createMutation.mutate({
        job_type: jobType,
        interval_seconds: intervalSeconds,
        endpoint_ids: null,
      });
    }
  };

  const columns: ColumnConfig<RecurringJob>[] = [
    { key: 'id', label: 'Job ID', sortable: false },
    { key: 'job_type', label: 'Type', sortable: true },
    { key: 'interval_seconds', label: 'Interval (sec)', sortable: true },
    {
      key: 'enabled',
      label: 'Status',
      sortable: false,
      render: (enabled) => (
        <span
          className={`px-2 py-1 rounded text-sm ${
            enabled
              ? 'bg-green-900 text-green-200'
              : 'bg-slate-700 text-slate-300'
          }`}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </span>
      ),
    },
    ...(canWrite ? [{
      key: 'id',
      label: 'Actions',
      sortable: false,
      render: (id, row) => (
        <div className="space-x-2 flex">
          <button
            onClick={() =>
              toggleMutation.mutate({
                jobId: String(id),
                enabled: !(row as RecurringJob).enabled,
              })
            }
            className="text-amber-400 hover:text-amber-300 text-sm"
          >
            {(row as RecurringJob).enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            onClick={() => deleteMutation.mutate(String(id))}
            className="text-red-400 hover:text-red-300 text-sm"
          >
            Delete
          </button>
        </div>
      ),
    } as ColumnConfig<RecurringJob>] : []),
  ];

  console.log('[RecurringPage] Render { jobs:', jobs.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">C2C Recurring Jobs</h1>
        <p className="text-slate-400 text-sm mt-1">
          Scheduled matrix runs and node health checks
        </p>
      </div>

      {canWrite && (
        <div className="flex gap-2">
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-sky-600 text-white rounded hover:bg-sky-700"
          >
            {showForm ? 'Cancel' : 'Create Job'}
          </button>
        </div>
      )}

      {showForm && canWrite && (
        <form
          onSubmit={handleCreate}
          className="bg-slate-800 p-4 rounded space-y-3 border border-slate-700"
        >
          <div>
            <label className="block text-amber-400 text-sm mb-1">Job Type *</label>
            <select
              value={jobType}
              onChange={(e) =>
                setJobType(e.target.value as 'matrix_run' | 'node_health')
              }
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
            >
              <option value="matrix_run">Matrix Run</option>
              <option value="node_health">Node Health</option>
            </select>
          </div>
          <div>
            <label className="block text-amber-400 text-sm mb-1">
              Interval (seconds) *
            </label>
            <input
              type="number"
              value={intervalSeconds}
              onChange={(e) => setIntervalSeconds(parseInt(e.target.value, 10))}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              min="30"
              step="30"
              required
            />
            <p className="text-slate-400 text-xs mt-1">Minimum: 30 seconds</p>
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
        data={jobs}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}

export { RecurringPage };
