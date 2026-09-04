import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import {
  createFeed,
  deleteFeed,
  FEED_SOURCE_TYPES,
  listFeeds,
  refreshFeed,
  type CreateFeedSourcePayload,
  type FeedSource,
} from '../../api/threatintel';

const feedsKey = ['threatintel', 'feeds'] as const;

interface FeedFormState {
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
}

const emptyForm: FeedFormState = {
  name: '',
  source_type: FEED_SOURCE_TYPES[0],
  url: '',
  enabled: true,
};

/**
 * FeedsPage — manages threat-intel feed sources (MISP/STIX/TAXII/CSV): list,
 * create, delete, and trigger an on-demand ingest refresh per source.
 */
export function FeedsPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form, setForm] = useState<FeedFormState>(emptyForm);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: feedsKey,
    queryFn: listFeeds,
    staleTime: 60 * 1000,
  });

  console.log('[FeedsPage] Render { count:', data.length, '}');

  const { mutate: saveFeed, isPending: isSaving } = useMutation({
    mutationFn: () => {
      const payload: CreateFeedSourcePayload = {
        name: form.name,
        source_type: form.source_type,
        url: form.url,
        enabled: form.enabled,
      };
      return createFeed(payload);
    },
    onSuccess: () => {
      console.log('[FeedsPage] SaveFeed success');
      queryClient.invalidateQueries({ queryKey: feedsKey });
      closeModal();
    },
    onError: (err) => {
      console.error('[FeedsPage] SaveFeed error', { error: String(err) });
      alert('Failed to create feed source');
    },
  });

  const { mutate: removeFeed } = useMutation({
    mutationFn: deleteFeed,
    onSuccess: (_result, feedId) => {
      console.log('[FeedsPage] DeleteFeed success { feedId }', { feedId });
      queryClient.invalidateQueries({ queryKey: feedsKey });
    },
    onError: (err) => {
      console.error('[FeedsPage] DeleteFeed error', { error: String(err) });
      alert('Failed to delete feed source');
    },
  });

  const { mutate: triggerRefresh } = useMutation({
    mutationFn: refreshFeed,
    onMutate: (feedId) => setRefreshingId(feedId),
    onSuccess: (result) => {
      console.log('[FeedsPage] RefreshFeed success { status, added, updated, errors }', {
        status: result.status,
        added: result.added,
        updated: result.updated,
        errors: result.errors,
      });
      queryClient.invalidateQueries({ queryKey: feedsKey });
    },
    onError: (err) => {
      console.error('[FeedsPage] RefreshFeed error', { error: String(err) });
      alert('Failed to refresh feed source');
    },
    onSettled: () => setRefreshingId(null),
  });

  const openCreateModal = () => {
    setForm(emptyForm);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setForm(emptyForm);
  };

  const handleSave = () => {
    if (!form.name.trim() || !form.url.trim()) {
      alert('Name and URL are required');
      return;
    }
    saveFeed();
  };

  const handleDelete = (feed: FeedSource) => {
    if (confirm(`Delete feed source "${feed.name}"?`)) {
      console.log('[FeedsPage] DeleteFeed { feedId }', { feedId: feed.id });
      removeFeed(feed.id);
    }
  };

  const handleRefresh = (feed: FeedSource) => {
    console.log('[FeedsPage] TriggerRefresh { feedId }', { feedId: feed.id });
    triggerRefresh(feed.id);
  };

  const columns: ColumnConfig<FeedSource>[] = [
    { key: 'name', label: 'Name', sortable: true },
    {
      key: 'source_type',
      label: 'Type',
      sortable: true,
      render: (sourceType) => (
        <span className="px-2 py-1 rounded text-sm bg-slate-700 text-amber-100 uppercase">
          {String(sourceType)}
        </span>
      ),
    },
    {
      key: 'url',
      label: 'URL',
      sortable: false,
      render: (url) => <span className="text-slate-300 font-mono text-xs">{String(url)}</span>,
    },
    {
      key: 'enabled',
      label: 'Enabled',
      sortable: true,
      render: (enabled) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            enabled ? 'bg-green-900 text-green-100' : 'bg-slate-700 text-slate-300'
          }`}
        >
          {enabled ? 'yes' : 'no'}
        </span>
      ),
    },
    {
      key: 'last_refresh_status',
      label: 'Last Refresh',
      sortable: true,
      render: (status, row) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            status === 'completed'
              ? 'bg-green-900 text-green-100'
              : status === 'failed'
                ? 'bg-red-900 text-red-100'
                : 'bg-slate-700 text-slate-300'
          }`}
          title={row.last_refresh_error ?? undefined}
        >
          {status ? String(status) : 'never'}
        </span>
      ),
    },
    {
      key: 'id',
      label: 'Actions',
      sortable: false,
      render: (_, row) => (
        <div className="flex gap-2">
          <button
            onClick={() => handleRefresh(row)}
            disabled={refreshingId === row.id}
            className="text-sky-400 hover:text-sky-300 transition-colors disabled:opacity-50"
            aria-label={`Refresh feed ${row.name}`}
          >
            <RefreshCw size={16} className={refreshingId === row.id ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => handleDelete(row)}
            className="text-red-400 hover:text-red-300 transition-colors"
            aria-label={`Delete feed ${row.name}`}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-amber-400">Feeds</h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none"
          aria-label="Add new feed source"
        >
          <Plus size={16} />
          Add Feed
        </button>
      </div>

      <div className="bg-slate-800 rounded-lg p-4">
        <DataTable
          columns={columns}
          data={data}
          isLoading={isLoading}
          error={error}
          onRetry={() => refetch()}
          pageSize={25}
        />
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h2 className="text-lg font-bold text-amber-400">Add Feed Source</h2>

            <div>
              <label htmlFor="feed-name" className="block text-sm text-slate-300 mb-1">
                Name
              </label>
              <input
                id="feed-name"
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="my-misp"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="feed-source-type" className="block text-sm text-slate-300 mb-1">
                Source Type
              </label>
              <select
                id="feed-source-type"
                value={form.source_type}
                onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              >
                {FEED_SOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="feed-url" className="block text-sm text-slate-300 mb-1">
                URL
              </label>
              <input
                id="feed-url"
                type="text"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://misp.example.com/export.json"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                id="feed-enabled"
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                className="rounded border-slate-600 focus:ring-2 focus:ring-sky-500"
              />
              <label htmlFor="feed-enabled" className="text-sm text-slate-300">
                Enabled
              </label>
            </div>

            <div className="flex gap-2 pt-4 border-t border-slate-600">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50 transition-colors"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={closeModal}
                className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
