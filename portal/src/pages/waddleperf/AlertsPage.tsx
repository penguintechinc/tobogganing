import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DataTable, ColumnConfig } from '../../components/DataTable';
import { useRole } from '../../hooks/useRole';
import {
  AlertRule,
  AlertChannel,
  AlertEvent,
  listAlertRules,
  createAlertRule,
  deleteAlertRule,
  listAlertChannels,
  createAlertChannel,
  deleteAlertChannel,
  listAlertEvents,
} from '../../api/wpcOps';

type Tab = 'rules' | 'channels' | 'events';

function RulesTab() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const {
    data: rules = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['alerts', 'rules'],
    queryFn: listAlertRules,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createAlertRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', 'rules'] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAlertRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', 'rules'] });
    },
  });

  const baseColumns: ColumnConfig<AlertRule>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'metric', label: 'Metric', sortable: true },
    { key: 'comparator', label: 'Operator', sortable: true },
    { key: 'threshold', label: 'Threshold', sortable: true },
    { key: 'window_seconds', label: 'Window (s)', sortable: true },
    {
      key: 'enabled',
      label: 'Status',
      render: (enabled) => (
        <span className={enabled ? 'text-green-400' : 'text-slate-400'}>
          {enabled ? 'Enabled' : 'Disabled'}
        </span>
      ),
    },
  ];

  const columns: ColumnConfig<AlertRule>[] = canWrite()
    ? [
        ...baseColumns,
        {
          key: 'id' as keyof AlertRule,
          label: 'Actions',
          render: (id) => (
            <button
              onClick={() => deleteMutation.mutate(id as string)}
              disabled={deleteMutation.isPending}
              className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
            >
              Delete
            </button>
          ),
        },
      ]
    : baseColumns;

  return (
    <div className="space-y-4">
      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded"
        >
          {showForm ? 'Cancel' : 'Add Rule'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            const payload: Parameters<typeof createMutation.mutate>[0] = {
              name: formData.get('name') as string,
              metric: formData.get('metric') as string,
              comparator: formData.get('comparator') as string,
              threshold: parseFloat(formData.get('threshold') as string),
              window_seconds: parseInt(formData.get('window_seconds') as string),
            };
            const deviceId = formData.get('device_id') as string;
            if (deviceId) payload.device_id = deviceId;
            const testType = formData.get('test_type') as string;
            if (testType) payload.test_type = testType;
            createMutation.mutate(payload);
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
        >
          <input
            name="name"
            placeholder="Rule name"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="metric"
            placeholder="Metric (e.g., latency_ms)"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <select
            name="comparator"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          >
            <option value="">Select operator</option>
            <option value="gt">Greater than</option>
            <option value="gte">Greater or equal</option>
            <option value="lt">Less than</option>
            <option value="lte">Less or equal</option>
          </select>
          <input
            name="threshold"
            type="number"
            placeholder="Threshold value"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="window_seconds"
            type="number"
            placeholder="Window seconds (default 300)"
            defaultValue="300"
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
        data={rules}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}

function ChannelsTab() {
  const { canWrite } = useRole();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [license402, setLicense402] = useState<string | null>(null);

  const {
    data: channels = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['alerts', 'channels'],
    queryFn: listAlertChannels,
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: createAlertChannel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', 'channels'] });
      setShowForm(false);
      setLicense402(null);
    },
    onError: (err: unknown) => {
      if (err && typeof err === 'object' && 'response' in err) {
        const response = err.response as Record<string, unknown> | undefined;
        if (response?.status === 402) {
          const data = response.data as Record<string, unknown> | undefined;
          const message = (data?.message as string | undefined) || 'Professional tier required';
          setLicense402(message);
        }
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAlertChannel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', 'channels'] });
    },
  });

  const baseChannelColumns: ColumnConfig<AlertChannel>[] = [
    { key: 'name', label: 'Name', sortable: true },
    {
      key: 'kind',
      label: 'Type',
      render: (kind) => (
        <span className={kind === 'webhook' ? 'text-amber-400' : 'text-blue-400'}>
          {kind === 'email' ? 'Email' : 'Webhook'}
        </span>
      ),
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
  ];

  const columns: ColumnConfig<AlertChannel>[] = canWrite()
    ? [
        ...baseChannelColumns,
        {
          key: 'id' as keyof AlertChannel,
          label: 'Actions',
          render: (id) => (
            <button
              onClick={() => deleteMutation.mutate(id as string)}
              disabled={deleteMutation.isPending}
              className="px-2 py-1 bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-200 rounded text-sm"
            >
              Delete
            </button>
          ),
        },
      ]
    : baseChannelColumns;

  return (
    <div className="space-y-4">
      {license402 && (
        <div className="bg-amber-900 border border-amber-700 text-amber-100 px-4 py-3 rounded">
          <p className="font-semibold">Professional License Required</p>
          <p className="text-sm">{license402}</p>
        </div>
      )}

      {canWrite() && (
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded"
        >
          {showForm ? 'Cancel' : 'Add Channel'}
        </button>
      )}

      {showForm && canWrite() && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            const kind = formData.get('kind') as string;
            const config =
              kind === 'email'
                ? { to: [formData.get('email_to') as string] }
                : { url: formData.get('webhook_url') as string };

            createMutation.mutate({
              name: formData.get('name') as string,
              kind: kind as 'email' | 'webhook',
              config,
            });
          }}
          className="bg-slate-800 p-4 rounded space-y-3"
        >
          <input
            name="name"
            placeholder="Channel name"
            required
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <select name="kind" required className="w-full px-3 py-2 bg-slate-700 text-white rounded">
            <option value="">Select type</option>
            <option value="email">Email</option>
            <option value="webhook">Webhook</option>
          </select>
          <input
            name="email_to"
            type="email"
            placeholder="Email address"
            className="w-full px-3 py-2 bg-slate-700 text-white rounded"
          />
          <input
            name="webhook_url"
            placeholder="Webhook URL"
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
        data={channels}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
      />
    </div>
  );
}

function EventsTab() {
  const {
    data: events = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['alerts', 'events'],
    queryFn: listAlertEvents,
    staleTime: 5 * 60 * 1000,
  });

  const columns: ColumnConfig<AlertEvent>[] = [
    { key: 'rule_id', label: 'Rule ID', sortable: true },
    { key: 'device_id', label: 'Device', sortable: true },
    { key: 'observed_value', label: 'Value', sortable: true },
    {
      key: 'fired_at',
      label: 'Fired At',
      render: (val) => new Date(val as string).toLocaleString(),
    },
    {
      key: 'notified',
      label: 'Notified',
      render: (val) => (
        <span className={val ? 'text-green-400' : 'text-slate-400'}>{val ? 'Yes' : 'No'}</span>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={events}
      isLoading={isLoading}
      error={error}
      onRetry={() => refetch()}
    />
  );
}

export function AlertsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('rules');

  console.log('[AlertsPage] Render { tab:', activeTab, '}');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-amber-400">Alerts</h1>
        <p className="text-slate-400 text-sm mt-1">Manage alert rules, channels, and events</p>
      </div>

      <div className="flex gap-2 border-b border-slate-700">
        {(['rules', 'channels', 'events'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-semibold transition-colors ${
              activeTab === tab
                ? 'text-amber-400 border-b-2 border-amber-400'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === 'rules' && <RulesTab />}
      {activeTab === 'channels' && <ChannelsTab />}
      {activeTab === 'events' && <EventsTab />}
    </div>
  );
}
