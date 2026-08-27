import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Edit2, Plus, Trash2 } from 'lucide-react';
import { DataTable, type ColumnConfig } from '../../components/DataTable';
import {
  createZone,
  deleteZone,
  listZones,
  updateZone,
  type CreateZonePayload,
  type Zone,
} from '../../api/netsvcs';
import { ZoneRecordsPage } from './ZoneRecordsPage';

const zonesKey = ['netsvcs', 'zones'] as const;

interface ZoneFormState {
  name: string;
  visibility: string;
  description: string;
}

const emptyForm: ZoneFormState = { name: '', visibility: 'public', description: '' };

/**
 * ZonesPage — lists DNS zones for the tenant with create/edit/delete and a
 * drilldown into each zone's records (ZoneRecordsPage).
 */
export function ZonesPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingZone, setEditingZone] = useState<Zone | null>(null);
  const [form, setForm] = useState<ZoneFormState>(emptyForm);

  const queryClient = useQueryClient();

  const {
    data = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: zonesKey,
    queryFn: listZones,
    staleTime: 5 * 60 * 1000,
  });

  console.log('[ZonesPage] Render { count:', data.length, '}');

  const { mutate: saveZone, isPending: isSaving } = useMutation({
    mutationFn: async () => {
      const payload: CreateZonePayload = {
        name: form.name,
        visibility: form.visibility,
        description: form.description || null,
      };
      if (editingZone) {
        return updateZone(editingZone.id, payload);
      }
      return createZone(payload);
    },
    onSuccess: () => {
      console.log('[ZonesPage] SaveZone success');
      queryClient.invalidateQueries({ queryKey: zonesKey });
      closeModal();
    },
    onError: (err) => {
      console.error('[ZonesPage] SaveZone error', { error: String(err) });
      alert('Failed to save zone');
    },
  });

  const { mutate: removeZone } = useMutation({
    mutationFn: deleteZone,
    onSuccess: (_result, zoneId) => {
      console.log('[ZonesPage] DeleteZone success { zoneId }', { zoneId });
      queryClient.invalidateQueries({ queryKey: zonesKey });
      if (expandedId === zoneId) {
        setExpandedId(null);
      }
    },
    onError: (err) => {
      console.error('[ZonesPage] DeleteZone error', { error: String(err) });
      alert('Failed to delete zone');
    },
  });

  const openCreateModal = () => {
    setEditingZone(null);
    setForm(emptyForm);
    setIsModalOpen(true);
  };

  const openEditModal = (zone: Zone) => {
    console.log('[ZonesPage] EditZone { zoneId }', { zoneId: zone.id });
    setEditingZone(zone);
    setForm({
      name: zone.name,
      visibility: zone.visibility,
      description: zone.description ?? '',
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingZone(null);
    setForm(emptyForm);
  };

  const handleSave = () => {
    if (!form.name.trim()) {
      alert('Zone name is required');
      return;
    }
    saveZone();
  };

  const handleDelete = (zone: Zone) => {
    if (confirm(`Delete zone "${zone.name}" and all its records?`)) {
      console.log('[ZonesPage] DeleteZone { zoneId }', { zoneId: zone.id });
      removeZone(zone.id);
    }
  };

  const columns: ColumnConfig<Zone>[] = [
    {
      key: 'name',
      label: 'Name',
      sortable: true,
      render: (_, row) => (
        <button
          onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
          className="flex items-center gap-2 text-amber-400 hover:text-amber-300"
          aria-label={`Toggle records for zone ${row.name}`}
        >
          {expandedId === row.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          {row.name}
        </button>
      ),
    },
    {
      key: 'visibility',
      label: 'Visibility',
      sortable: true,
      render: (visibility) => (
        <span
          className={`px-2 py-1 rounded text-sm font-medium ${
            visibility === 'public' ? 'bg-blue-900 text-blue-100' : 'bg-slate-700 text-slate-200'
          }`}
        >
          {String(visibility)}
        </span>
      ),
    },
    {
      key: 'description',
      label: 'Description',
      sortable: false,
      render: (description) => <span className="text-slate-300">{String(description ?? '-')}</span>,
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
        <div className="flex gap-2">
          <button
            onClick={() => openEditModal(row)}
            className="text-amber-400 hover:text-amber-300 transition-colors"
            aria-label={`Edit zone ${row.name}`}
          >
            <Edit2 size={16} />
          </button>
          <button
            onClick={() => handleDelete(row)}
            className="text-red-400 hover:text-red-300 transition-colors"
            aria-label={`Delete zone ${row.name}`}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  const expandedZone = data.find((z) => z.id === expandedId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-amber-400">Zones</h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors"
          aria-label="Add new zone"
        >
          <Plus size={16} />
          Add Zone
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

      {expandedZone && (
        <div className="bg-slate-800 rounded-lg p-4">
          <ZoneRecordsPage
            zoneId={expandedZone.id}
            zoneName={expandedZone.name}
            onClose={() => setExpandedId(null)}
          />
        </div>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h2 className="text-lg font-bold text-amber-400">
              {editingZone ? 'Edit Zone' : 'Add Zone'}
            </h2>

            <div>
              <label className="block text-sm text-slate-300 mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="example.com"
                disabled={!!editingZone}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none disabled:opacity-50"
              />
            </div>

            <div>
              <label htmlFor="zone-visibility" className="block text-sm text-slate-300 mb-1">
                Visibility
              </label>
              <select
                id="zone-visibility"
                value={form.visibility}
                onChange={(e) => setForm({ ...form, visibility: e.target.value })}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              >
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </div>

            <div>
              <label htmlFor="zone-description" className="block text-sm text-slate-300 mb-1">
                Description
              </label>
              <textarea
                id="zone-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
                placeholder="Optional description"
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
