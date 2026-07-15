import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { Device, listDevices } from '../../api/waddleperf';

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return 'Never';
  const date = new Date(isoString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function StatusBadge({ status }: { status: string }) {
  const colorClass =
    status === 'online'
      ? 'bg-green-900 text-green-200'
      : status === 'offline'
        ? 'bg-red-900 text-red-200'
        : 'bg-yellow-900 text-yellow-200';

  return (
    <span className={`px-2 py-1 rounded text-sm ${colorClass}`}>
      {status}
    </span>
  );
}

export function DevicesPage() {
  const {
    data: devices = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['waddleperf', 'devices'],
    queryFn: listDevices,
    staleTime: 5 * 60 * 1000,
  });

  const columns: ColumnConfig<Device>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'org_unit_id', label: 'Org Unit', sortable: true },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (status) => <StatusBadge status={String(status)} />,
    },
    {
      key: 'last_heartbeat',
      label: 'Last Heartbeat',
      sortable: true,
      render: (heartbeat) =>
        formatRelativeTime(heartbeat as string | null),
    },
  ];

  console.log('[DevicesPage] Render { devices:', devices.length, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Devices</h1>
        <p className="text-slate-400 text-sm mt-1">
          Manage and monitor WaddlePerf cluster devices
        </p>
      </div>

      <DataTable
        columns={columns}
        data={devices}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}
