import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit2, Plus, Trash2 } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import {
  createRecord,
  deleteRecord,
  listRecords,
  updateRecord,
  type CreateRecordPayload,
  type DnsRecord,
} from '../../api/netsvcs';

const RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'NS'] as const;

interface RecordFormState {
  name: string;
  type: string;
  value: string;
  ttl: string;
  priority: string;
  weight: string;
  port: string;
}

const emptyForm: RecordFormState = {
  name: '',
  type: 'A',
  value: '',
  ttl: '300',
  priority: '',
  weight: '',
  port: '',
};

export interface ZoneRecordsPageProps {
  zoneId: string;
  zoneName: string;
  onClose: () => void;
}

/**
 * ZoneRecordsPage — drilldown from ZonesPage showing a zone's records with
 * create/edit/delete support (A/AAAA/CNAME/MX/TXT/SRV/NS).
 */
export function ZoneRecordsPage({ zoneId, zoneName, onClose }: ZoneRecordsPageProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<DnsRecord | null>(null);
  const [form, setForm] = useState<RecordFormState>(emptyForm);

  const queryClient = useQueryClient();
  const recordsKey = ['netsvcs', 'records', zoneId] as const;

  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: recordsKey,
    queryFn: () => listRecords(zoneId),
    staleTime: 60 * 1000,
  });

  console.log('[ZoneRecordsPage] Render { zoneId:', zoneId, 'count:', data.length, '}');

  const { mutate: saveRecord, isPending: isSaving } = useMutation({
    mutationFn: async () => {
      const payload: CreateRecordPayload = {
        name: form.name,
        type: form.type,
        value: form.value,
        ttl: form.ttl ? Number(form.ttl) : 300,
        priority: form.priority ? Number(form.priority) : null,
        weight: form.weight ? Number(form.weight) : null,
        port: form.port ? Number(form.port) : null,
      };
      if (editingRecord) {
        return updateRecord(zoneId, editingRecord.id, payload);
      }
      return createRecord(zoneId, payload);
    },
    onSuccess: () => {
      console.log('[ZoneRecordsPage] SaveRecord success { zoneId }', { zoneId });
      queryClient.invalidateQueries({ queryKey: recordsKey });
      closeModal();
    },
    onError: (err) => {
      console.error('[ZoneRecordsPage] SaveRecord error', { error: String(err) });
      alert('Failed to save record');
    },
  });

  const { mutate: removeRecord } = useMutation({
    mutationFn: (recordId: string) => deleteRecord(zoneId, recordId),
    onSuccess: () => {
      console.log('[ZoneRecordsPage] DeleteRecord success { zoneId }', { zoneId });
      queryClient.invalidateQueries({ queryKey: recordsKey });
    },
    onError: (err) => {
      console.error('[ZoneRecordsPage] DeleteRecord error', { error: String(err) });
      alert('Failed to delete record');
    },
  });

  const openCreateModal = () => {
    setEditingRecord(null);
    setForm(emptyForm);
    setIsModalOpen(true);
  };

  const openEditModal = (record: DnsRecord) => {
    console.log('[ZoneRecordsPage] EditRecord { recordId }', { recordId: record.id });
    setEditingRecord(record);
    setForm({
      name: record.name,
      type: record.type,
      value: record.value,
      ttl: String(record.ttl),
      priority: record.priority !== null ? String(record.priority) : '',
      weight: record.weight !== null ? String(record.weight) : '',
      port: record.port !== null ? String(record.port) : '',
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingRecord(null);
    setForm(emptyForm);
  };

  const handleSave = () => {
    if (!form.name.trim() || !form.value.trim()) {
      alert('Record name and value are required');
      return;
    }
    saveRecord();
  };

  const handleDelete = (record: DnsRecord) => {
    if (confirm(`Delete record "${record.name}" (${record.type})?`)) {
      console.log('[ZoneRecordsPage] DeleteRecord { recordId }', { recordId: record.id });
      removeRecord(record.id);
    }
  };

  const columns: ColumnConfig<DnsRecord>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'type', label: 'Type', sortable: true },
    { key: 'value', label: 'Value', sortable: false },
    { key: 'ttl', label: 'TTL', sortable: true },
    {
      key: 'priority',
      label: 'Priority/Weight/Port',
      sortable: false,
      render: (_, row) =>
        [row.priority, row.weight, row.port].filter((v) => v !== null).join(' / ') || '-',
    },
    {
      key: 'id',
      label: 'Actions',
      sortable: false,
      render: (_, row) => (
        <div className="flex gap-2">
          <button
            onClick={() => openEditModal(row)}
            className="text-amber-400 hover:text-amber-300 transition-colors"
            aria-label={`Edit record ${row.name}`}
          >
            <Edit2 size={16} />
          </button>
          <button
            onClick={() => handleDelete(row)}
            className="text-red-400 hover:text-red-300 transition-colors"
            aria-label={`Delete record ${row.name}`}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-amber-400">Records: {zoneName}</h2>
        <div className="flex gap-2">
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors text-sm"
            aria-label="Add new record"
          >
            <Plus size={14} />
            Add Record
          </button>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200"
            aria-label="Close records"
          >
            ✕
          </button>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={data}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        pageSize={10}
      />

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h2 className="text-lg font-bold text-amber-400">
              {editingRecord ? 'Edit Record' : 'Add Record'}
            </h2>

            <div>
              <label className="block text-sm text-slate-300 mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="www"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm text-slate-300 mb-1">Type</label>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              >
                {RECORD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-slate-300 mb-1">Value</label>
              <input
                type="text"
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                placeholder="1.2.3.4"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="record-ttl" className="block text-sm text-slate-300 mb-1">
                TTL (seconds)
              </label>
              <input
                id="record-ttl"
                type="number"
                value={form.ttl}
                onChange={(e) => setForm({ ...form, ttl: e.target.value })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              />
            </div>

            {(form.type === 'MX' || form.type === 'SRV') && (
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label htmlFor="record-priority" className="block text-sm text-slate-300 mb-1">
                    Priority
                  </label>
                  <input
                    id="record-priority"
                    type="number"
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value })}
                    className="w-full bg-slate-700 text-white px-2 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                  />
                </div>
                {form.type === 'SRV' && (
                  <>
                    <div>
                      <label htmlFor="record-weight" className="block text-sm text-slate-300 mb-1">
                        Weight
                      </label>
                      <input
                        id="record-weight"
                        type="number"
                        value={form.weight}
                        onChange={(e) => setForm({ ...form, weight: e.target.value })}
                        className="w-full bg-slate-700 text-white px-2 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                      />
                    </div>
                    <div>
                      <label htmlFor="record-port" className="block text-sm text-slate-300 mb-1">
                        Port
                      </label>
                      <input
                        id="record-port"
                        type="number"
                        value={form.port}
                        onChange={(e) => setForm({ ...form, port: e.target.value })}
                        className="w-full bg-slate-700 text-white px-2 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                      />
                    </div>
                  </>
                )}
              </div>
            )}

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
