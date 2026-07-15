import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import { MatrixGrid } from './MatrixGrid';
import {
  Run,
  listRuns,
  createRun,
  getRunMatrix,
  CreateRunPayload,
  MatrixCell,
} from '../../api/c2c';

function RunsPage() {
  const { canWrite: canWriteFn } = useRole();
  const canWrite = canWriteFn();
  const [showForm, setShowForm] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [matrixData, setMatrixData] = useState<{ regions: string[]; cells: MatrixCell[] } | null>(null);
  const [testTypes, setTestTypes] = useState<string>('latency');

  const queryClient = useQueryClient();

  const {
    data: runs = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['c2c', 'runs'],
    queryFn: listRuns,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['c2c', 'runs'] });
      setShowForm(false);
      setTestTypes('latency');
    },
  });

  const matrixMutation = useMutation({
    mutationFn: (runId: string) => getRunMatrix(runId),
    onSuccess: (data) => {
      setMatrixData(data);
    },
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const testTypesList = testTypes
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t);
    if (testTypesList.length > 0) {
      const payload: CreateRunPayload = {
        test_types: testTypesList,
      };
      createMutation.mutate(payload);
    }
  };

  const handleExpandRun = (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      setMatrixData(null);
    } else {
      setExpandedRunId(runId);
      matrixMutation.mutate(runId);
    }
  };

  const columns: ColumnConfig<Run>[] = [
    { key: 'id', label: 'Run ID', sortable: true },
    { key: 'status', label: 'Status', sortable: true },
    { key: 'total_pairs', label: 'Total Pairs', sortable: true },
    { key: 'created_at', label: 'Created', sortable: true },
    {
      key: 'id',
      label: 'Details',
      sortable: false,
      render: (id) => (
        <button
          onClick={() => handleExpandRun(String(id))}
          className="text-sky-400 hover:text-sky-300"
        >
          {expandedRunId === id ? 'Hide' : 'Show'} Matrix
        </button>
      ),
    },
  ];

  console.log('[RunsPage] Render { runs:', runs.length, ', expanded:', expandedRunId, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">C2C Runs</h1>
        <p className="text-slate-400 text-sm mt-1">
          Cluster-to-cluster matrix runs and results
        </p>
      </div>

      {canWrite && (
        <div className="flex gap-2">
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-sky-600 text-white rounded hover:bg-sky-700"
          >
            {showForm ? 'Cancel' : 'Create Run'}
          </button>
        </div>
      )}

      {showForm && canWrite && (
        <form
          onSubmit={handleCreate}
          className="bg-slate-800 p-4 rounded space-y-3 border border-slate-700"
        >
          <div>
            <label className="block text-amber-400 text-sm mb-1">
              Test Types (comma-separated) *
            </label>
            <input
              type="text"
              value={testTypes}
              onChange={(e) => setTestTypes(e.target.value)}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded"
              placeholder="latency, throughput"
              required
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
        data={runs}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />

      {expandedRunId && matrixData && (
        <div className="bg-slate-800 p-4 rounded border border-slate-700">
          <h3 className="text-amber-400 font-semibold mb-3">
            Matrix Results for Run {expandedRunId}
          </h3>
          {matrixMutation.isPending ? (
            <div className="text-slate-400">Loading matrix data...</div>
          ) : (
            <MatrixGrid
              regions={matrixData.regions}
              cells={matrixData.cells}
              testType="latency"
            />
          )}
        </div>
      )}
    </div>
  );
}

export { RunsPage };
