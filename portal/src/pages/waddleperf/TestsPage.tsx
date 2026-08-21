import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Test, listTests } from '../../api/waddleperf';
import { ChevronDown, ChevronRight } from 'lucide-react';

function DetailPanel({ test }: { test: Test }) {
  return (
    <div className="bg-slate-700 px-4 py-3 space-y-2">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-slate-400 text-sm">Test ID</p>
          <p className="text-amber-400 font-mono">{test.id}</p>
        </div>
        <div>
          <p className="text-slate-400 text-sm">Test Type</p>
          <p className="text-slate-200">{test.test_type}</p>
        </div>
        <div>
          <p className="text-slate-400 text-sm">Latency</p>
          <p className="text-slate-200">
            {test.latency_ms !== null ? `${test.latency_ms}ms` : 'N/A'}
          </p>
        </div>
        <div>
          <p className="text-slate-400 text-sm">Throughput</p>
          <p className="text-slate-200">{test.throughput !== null ? test.throughput : 'N/A'}</p>
        </div>
        {test.target && (
          <div className="col-span-2">
            <p className="text-slate-400 text-sm">Target</p>
            <p className="text-slate-200 break-all">{test.target}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function TestRow({
  test,
  expanded,
  onToggle,
}: {
  test: Test;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        data-testid="datatable-row"
        className="border-b border-slate-700 hover:bg-slate-700 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-4 py-3 text-slate-200 w-8">
          {expanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        </td>
        <td className="px-4 py-3 text-slate-200">{test.id.substring(0, 8)}...</td>
        <td className="px-4 py-3 text-slate-200">{test.device_id.substring(0, 8)}...</td>
        <td className="px-4 py-3 text-slate-200">{test.test_type}</td>
        <td className="px-4 py-3">
          <span
            className={`px-2 py-1 rounded text-sm ${
              test.status === 'completed'
                ? 'bg-green-900 text-green-200'
                : test.status === 'pending'
                  ? 'bg-yellow-900 text-yellow-200'
                  : 'bg-red-900 text-red-200'
            }`}
          >
            {test.status}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-slate-700">
          <td colSpan={5} className="p-0">
            <DetailPanel test={test} />
          </td>
        </tr>
      )}
    </>
  );
}

export function TestsPage() {
  const {
    data: tests = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['waddleperf', 'tests'],
    queryFn: listTests,
    staleTime: 5 * 60 * 1000,
  });

  const [expandedId, setExpandedId] = useState<string | null>(null);

  console.log('[TestsPage] Render { tests:', tests.length, '}');

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">Tests</h1>
        </div>
        <div data-testid="datatable" className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-700 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">Tests</h1>
        </div>
        <div
          data-testid="datatable"
          className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded"
        >
          <p className="font-semibold">Error loading tests</p>
          <p className="text-sm">{error.message}</p>
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

  if (tests.length === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-amber-400">Tests</h1>
        </div>
        <div data-testid="datatable" className="text-center py-8 text-amber-300">
          <p>No tests available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Tests</h1>
        <p className="text-slate-400 text-sm mt-1">View performance test results and metrics</p>
      </div>

      <div data-testid="datatable" className="overflow-x-auto border border-slate-700 rounded">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-slate-800 border-b border-slate-700">
              <th className="px-4 py-3 text-left w-8"></th>
              <th className="px-4 py-3 text-left text-amber-400 font-semibold">Test ID</th>
              <th className="px-4 py-3 text-left text-amber-400 font-semibold">Device ID</th>
              <th className="px-4 py-3 text-left text-amber-400 font-semibold">Type</th>
              <th className="px-4 py-3 text-left text-amber-400 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {tests.map((test) => (
              <TestRow
                key={test.id}
                test={test}
                expanded={expandedId === test.id}
                onToggle={() => setExpandedId(expandedId === test.id ? null : test.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
