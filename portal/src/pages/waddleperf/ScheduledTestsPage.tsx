import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  ScheduledTest,
  listScheduledTests,
  createScheduledTest,
  deleteScheduledTest,
  updateScheduledTest,
} from '../../api/wpcOps';

export function ScheduledTestsPage() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const {
    data: tests = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['scheduled-tests'],
    queryFn: listScheduledTests,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createScheduledTest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tests'] });
      setShowForm(false);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (test: ScheduledTest) => updateScheduledTest(test.id, { enabled: !test.enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tests'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteScheduledTest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tests'] });
    },
  });

  const baseTestColumns: ColumnConfig<ScheduledTest>[] = [
    { key: 'device_id', label: 'Device', sortable: true },
    { key: 'test_type', label: 'Test Type', sortable: true },
    { key: 'target', label: 'Target', sortable: true },
    {
      key: 'interval_seconds',
      label: 'Interval (s)',
      sortable: true,
    },
    {
      key: 'enabled',
      label: 'Status',
      render: (enabled) => (
        <span className={enabled ? 'text-green-400' : 'text-slate-400'}>
          {enabled ? 'Enabled' : 'Disabled'}
        </span>
      ),
    },
    {
      key: 'next_run_at',
      label: 'Next Run',
      render: (val) => new Date(val as string).toLocaleString(),
    },
  ];

  const columns: ColumnConfig<ScheduledTest>[] = canWrite()
    ? [
        ...baseTestColumns,
        {
          key: 'id' as keyof ScheduledTest,
          label: 'Actions',
          render: (_id, test) => (
            <div className="flex gap-2">
              <button
                onClick={() => toggleMutation.mutate(test)}
                disabled={toggleMutation.isPending}
                className="px-2 py-1 bg-blue-900 hover:bg-blue-800 disabled:opacity-50 text-blue-200 rounded text-sm"
              >
                {test.enabled ? 'Disable' : 'Enable'}
              </button>
              <button
                onClick={() => deleteMutation.mutate(test.id)}
                disabled={deleteMutation.isPending}
                className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
              >
                Delete
              </button>
            </div>
          ),
        },
      ]
    : baseTestColumns;

  console.log('[ScheduledTestsPage] Render { tests:', tests.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Scheduled Tests</h1>
        <p className="text-slate-400 text-sm mt-1">Manage recurring device tests</p>
      </div>

      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded"
        >
          {showForm ? 'Cancel' : 'Create Test'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            createMutation.mutate({
              device_id: formData.get('device_id') as string,
              test_type: formData.get('test_type') as string,
              target: formData.get('target') as string,
              interval_seconds: parseInt(formData.get('interval_seconds') as string),
            });
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
        >
          <input
            name="device_id"
            placeholder="Device ID"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="test_type"
            placeholder="Test type"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="target"
            placeholder="Target URL or endpoint"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="interval_seconds"
            type="number"
            placeholder="Interval (seconds, min 30)"
            min="30"
            required
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
        data={tests}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}
