import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import {
  addBlocklistEntry,
  deleteBlocklistEntry,
  IOC_TYPES,
  listBlocklist,
  type BlocklistEntry,
  type BlocklistFilters,
  type CreateBlocklistEntryPayload,
} from '../../api/threatintel';

const blocklistKey = (filters: BlocklistFilters) => ['threatintel', 'blocklist', filters] as const;

interface EntryFormState {
  indicator_type: string;
  value: string;
  source: string;
  confidence: number;
}

const emptyForm: EntryFormState = {
  indicator_type: IOC_TYPES[0],
  value: '',
  source: 'manual',
  confidence: 100,
};

/**
 * BlocklistPage — manages manual blocklist entries: filter by indicator type
 * / source, add new entries, and remove existing ones.
 */
export function BlocklistPage() {
  const [typeFilter, setTypeFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form, setForm] = useState<EntryFormState>(emptyForm);

  const queryClient = useQueryClient();

  const filters: BlocklistFilters = {
    ...(typeFilter ? { indicator_type: typeFilter } : {}),
    ...(sourceFilter ? { source: sourceFilter } : {}),
  };
  const queryKey = blocklistKey(filters);

  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: () => listBlocklist(filters),
    staleTime: 60 * 1000,
  });

  console.log('[BlocklistPage] Render { count:', data.length, '}');

  const { mutate: saveEntry, isPending: isSaving } = useMutation({
    mutationFn: () => {
      const payload: CreateBlocklistEntryPayload = {
        indicator_type: form.indicator_type,
        value: form.value,
        source: form.source || 'manual',
        confidence: form.confidence,
      };
      return addBlocklistEntry(payload);
    },
    onSuccess: () => {
      console.log('[BlocklistPage] SaveEntry success');
      queryClient.invalidateQueries({ queryKey: ['threatintel', 'blocklist'] });
      closeModal();
    },
    onError: (err) => {
      console.error('[BlocklistPage] SaveEntry error', { error: String(err) });
      alert('Failed to add blocklist entry');
    },
  });

  const { mutate: removeEntry } = useMutation({
    mutationFn: deleteBlocklistEntry,
    onSuccess: (_result, entryId) => {
      console.log('[BlocklistPage] DeleteEntry success { entryId }', { entryId });
      queryClient.invalidateQueries({ queryKey: ['threatintel', 'blocklist'] });
    },
    onError: (err) => {
      console.error('[BlocklistPage] DeleteEntry error', { error: String(err) });
      alert('Failed to delete blocklist entry');
    },
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
    if (!form.value.trim()) {
      alert('Indicator value is required');
      return;
    }
    saveEntry();
  };

  const handleDelete = (entry: BlocklistEntry) => {
    if (confirm(`Remove blocklist entry "${entry.value}"?`)) {
      console.log('[BlocklistPage] DeleteEntry { entryId }', { entryId: entry.id });
      removeEntry(entry.id);
    }
  };

  const columns: ColumnConfig<BlocklistEntry>[] = [
    { key: 'indicator_type', label: 'Type', sortable: true },
    {
      key: 'value',
      label: 'Value',
      sortable: true,
      render: (value) => <span className="font-mono text-slate-200">{String(value)}</span>,
    },
    { key: 'source', label: 'Source', sortable: true },
    { key: 'confidence', label: 'Confidence', sortable: true },
    {
      key: 'active',
      label: 'Active',
      sortable: true,
      render: (active) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            active ? 'bg-green-900 text-green-100' : 'bg-slate-700 text-slate-300'
          }`}
        >
          {active ? 'yes' : 'no'}
        </span>
      ),
    },
    {
      key: 'created_at',
      label: 'Created',
      sortable: true,
      render: (createdAt) => new Date(String(createdAt)).toLocaleString(),
    },
    {
      key: 'id',
      label: 'Actions',
      sortable: false,
      render: (_, row) => (
        <button
          onClick={() => handleDelete(row)}
          className="text-red-400 hover:text-red-300 transition-colors"
          aria-label={`Delete blocklist entry ${row.value}`}
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-amber-400">Blocklist</h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none"
          aria-label="Add blocklist entry"
        >
          <Plus size={16} />
          Add Entry
        </button>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 flex flex-col sm:flex-row gap-3">
        <div className="w-full sm:w-40">
          <label htmlFor="blocklist-type-filter" className="block text-sm text-slate-300 mb-1">
            Type
          </label>
          <select
            id="blocklist-type-filter"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
          >
            <option value="">All types</option>
            {IOC_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="blocklist-source-filter" className="block text-sm text-slate-300 mb-1">
            Source
          </label>
          <input
            id="blocklist-source-filter"
            type="text"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            placeholder="Filter by source"
            className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
          />
        </div>
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
            <h2 className="text-lg font-bold text-amber-400">Add Blocklist Entry</h2>

            <div>
              <label htmlFor="entry-type" className="block text-sm text-slate-300 mb-1">
                Type
              </label>
              <select
                id="entry-type"
                value={form.indicator_type}
                onChange={(e) => setForm({ ...form, indicator_type: e.target.value })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              >
                {IOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="entry-value" className="block text-sm text-slate-300 mb-1">
                Value
              </label>
              <input
                id="entry-value"
                type="text"
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                placeholder="malicious.example.com"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="entry-source" className="block text-sm text-slate-300 mb-1">
                Source
              </label>
              <input
                id="entry-source"
                type="text"
                value={form.source}
                onChange={(e) => setForm({ ...form, source: e.target.value })}
                placeholder="manual"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="entry-confidence" className="block text-sm text-slate-300 mb-1">
                Confidence
              </label>
              <input
                id="entry-confidence"
                type="number"
                min={0}
                max={100}
                value={form.confidence}
                onChange={(e) => setForm({ ...form, confidence: Number(e.target.value) })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
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
