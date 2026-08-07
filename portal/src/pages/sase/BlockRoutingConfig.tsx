import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2, Plus, Edit2 } from 'lucide-react';
import {
  listBlockPages,
  listBlockRoutes,
  upsertBlockRoutes,
  type BlockRoute,
  type BlockRouteMetadata,
} from '../../api/sase';

/**
 * BlockRoutingConfig — source_type → destination routing table
 *
 * Displays a table mapping block sources (source_type) to destinations
 * (internal pages or external URLs) with governance metadata fields.
 * Supports CRUD operations for route management.
 */
export function BlockRoutingConfig() {
  const [editingRoute, setEditingRoute] = useState<BlockRoute | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRoute, setNewRoute] = useState({
    source_type: '',
    destination_kind: 'page' as 'page' | 'external',
    page_id: '',
    external_url: '',
    ticket: '',
    notes: '',
    expiry: '',
    review_date: '',
    scope: '',
    risk: '',
  });

  const queryClient = useQueryClient();

  console.log('[BlockRoutingConfig] Render { routes }', { routes: '[querying...]' });

  // Load pages and routes
  const { data: pages = [] } = useQuery({
    queryKey: ['blockpages', 'pages'],
    queryFn: listBlockPages,
  });

  const { data: routes = [] } = useQuery({
    queryKey: ['blockpages', 'routes'],
    queryFn: listBlockRoutes,
  });

  // Upsert routes mutation
  const { mutate: saveRoutes, isPending } = useMutation({
    mutationFn: upsertBlockRoutes,
    onSuccess: () => {
      console.log('[BlockRoutingConfig] SaveRoutes success');
      queryClient.invalidateQueries({ queryKey: ['blockpages', 'routes'] });
      setIsModalOpen(false);
      setEditingRoute(null);
      setNewRoute({
        source_type: '',
        destination_kind: 'page',
        page_id: '',
        external_url: '',
        ticket: '',
        notes: '',
        expiry: '',
        review_date: '',
        scope: '',
        risk: '',
      });
    },
    onError: (error) => {
      console.error('[BlockRoutingConfig] SaveRoutes error', { error: String(error) });
      alert('Failed to save routes');
    },
  });

  // Open modal for new route
  const handleAddRoute = () => {
    setEditingRoute(null);
    setNewRoute({
      source_type: '',
      destination_kind: 'page',
      page_id: '',
      external_url: '',
      ticket: '',
      notes: '',
      expiry: '',
      review_date: '',
      scope: '',
      risk: '',
    });
    setIsModalOpen(true);
  };

  // Open modal for editing route
  const handleEditRoute = (route: BlockRoute) => {
    console.log('[BlockRoutingConfig] EditRoute { sourceType }', { sourceType: route.source_type });
    setEditingRoute(route);
    setNewRoute({
      source_type: route.source_type,
      destination_kind: route.destination_kind,
      page_id: route.page_id || '',
      external_url: route.external_url || '',
      ticket: route.ticket || '',
      notes: route.notes || '',
      expiry: route.expiry || '',
      review_date: route.review_date || '',
      scope: route.scope || '',
      risk: route.risk || '',
    });
    setIsModalOpen(true);
  };

  // Save route
  const handleSaveRoute = () => {
    if (!newRoute.source_type.trim()) {
      alert('Source type is required');
      return;
    }

    if (newRoute.destination_kind === 'page' && !newRoute.page_id) {
      alert('Page selection is required');
      return;
    }

    if (newRoute.destination_kind === 'external' && !newRoute.external_url.trim()) {
      alert('External URL is required');
      return;
    }

    // Build metadata object with only non-empty values
    const metadata: BlockRouteMetadata = {};
    if (newRoute.ticket) metadata.ticket = newRoute.ticket;
    if (newRoute.notes) metadata.notes = newRoute.notes;
    if (newRoute.expiry) metadata.expiry = newRoute.expiry;
    if (newRoute.review_date) metadata.review_date = newRoute.review_date;
    if (newRoute.scope) metadata.scope = newRoute.scope;
    if (newRoute.risk) metadata.risk = newRoute.risk;

    // For editing: filter out the old route; for creating: keep all
    const existingRoutes = editingRoute
      ? routes.filter((r) => r.source_type !== editingRoute.source_type)
      : routes;

    // Build upsert payload (not trying to be BlockRoute objects - the server returns those)
    const routesToUpsert = existingRoutes
      .map((r) => ({
        source_type: r.source_type,
        destination_kind: r.destination_kind,
        page_id: r.page_id,
        external_url: r.external_url,
        metadata: {
          ticket: r.ticket,
          notes: r.notes,
          expiry: r.expiry,
          review_date: r.review_date,
          scope: r.scope,
          risk: r.risk,
        } as BlockRouteMetadata | undefined,
      }))
      .concat([
        {
          source_type: newRoute.source_type,
          destination_kind: newRoute.destination_kind,
          page_id: newRoute.destination_kind === 'page' ? newRoute.page_id : (null as string | null),
          external_url: newRoute.destination_kind === 'external' ? newRoute.external_url : (null as string | null),
          metadata: Object.keys(metadata).length > 0 ? metadata : (undefined as BlockRouteMetadata | undefined),
        },
      ]);

    // Remove empty metadata from all routes
    const finalRoutes = routesToUpsert.map((r) => {
      if (r.metadata) {
        const hasMetadata = Object.values(r.metadata).some((v) => v !== undefined && v !== null && v !== '');
        if (!hasMetadata) {
          r.metadata = undefined;
        }
      }
      return r;
    });

    console.log('[BlockRoutingConfig] SaveRoute { sourceType }', { sourceType: newRoute.source_type });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    saveRoutes(finalRoutes as any);
  };

  // Delete route
  const handleDeleteRoute = (sourceType: string) => {
    if (confirm(`Delete route for "${sourceType}"?`)) {
      const remainingRoutes = routes.filter((r) => r.source_type !== sourceType);
      console.log('[BlockRoutingConfig] DeleteRoute { sourceType }', { sourceType });

      const routesToUpsert = remainingRoutes.map((r) => ({
        source_type: r.source_type,
        destination_kind: r.destination_kind,
        page_id: r.page_id,
        external_url: r.external_url,
        metadata: {
          ticket: r.ticket,
          notes: r.notes,
          expiry: r.expiry,
          review_date: r.review_date,
          scope: r.scope,
          risk: r.risk,
        } as BlockRouteMetadata | undefined,
      }));

      // Remove empty metadata
      const finalRoutes = routesToUpsert.map((r) => {
        if (r.metadata) {
          const hasMetadata = Object.values(r.metadata).some((v) => v !== undefined && v !== null && v !== '');
          if (!hasMetadata) {
            r.metadata = undefined;
          }
        }
        return r;
      });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      saveRoutes(finalRoutes as any);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-amber-400">Block Routing Config</h1>
        <button
          onClick={handleAddRoute}
          className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors"
          aria-label="Add new route"
        >
          <Plus size={16} />
          Add Route
        </button>
      </div>

      {/* Routes Table */}
      {routes.length > 0 ? (
        <div className="bg-slate-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-700 border-b border-slate-600">
                <th className="px-4 py-3 text-left text-amber-400 font-semibold">Source Type</th>
                <th className="px-4 py-3 text-left text-amber-400 font-semibold">Destination</th>
                <th className="px-4 py-3 text-left text-amber-400 font-semibold">Kind</th>
                <th className="px-4 py-3 text-left text-amber-400 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((route, idx) => (
                <tr
                  key={route.id}
                  className={`border-b border-slate-600 ${idx % 2 === 0 ? 'bg-slate-800' : 'bg-slate-750'}`}
                >
                  <td className="px-4 py-3 text-slate-100 font-mono text-xs">{route.source_type}</td>
                  <td className="px-4 py-3 text-slate-300">
                    {route.destination_kind === 'page'
                      ? pages.find((p) => p.id === route.page_id)?.name || route.page_id
                      : route.external_url}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        route.destination_kind === 'page'
                          ? 'bg-blue-900 text-blue-100'
                          : 'bg-green-900 text-green-100'
                      }`}
                    >
                      {route.destination_kind}
                    </span>
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button
                      onClick={() => handleEditRoute(route)}
                      className="text-amber-400 hover:text-amber-300 transition-colors"
                      aria-label={`Edit route for ${route.source_type}`}
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleDeleteRoute(route.source_type)}
                      className="text-red-400 hover:text-red-300 transition-colors"
                      aria-label={`Delete route for ${route.source_type}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-lg p-8 text-center text-slate-400">
          No routes configured. Add one to get started.
        </div>
      )}

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full space-y-4">
            <h2 className="text-lg font-bold text-amber-400">
              {editingRoute ? 'Edit Route' : 'Add Route'}
            </h2>

            {/* Source Type */}
            <div>
              <label className="block text-sm text-slate-300 mb-1">Source Type</label>
              <input
                type="text"
                value={newRoute.source_type}
                onChange={(e) =>
                  setNewRoute({
                    ...newRoute,
                    source_type: e.target.value,
                  })
                }
                placeholder="e.g., web-category:gambling"
                disabled={!!editingRoute}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none disabled:opacity-50"
              />
            </div>

            {/* Destination Kind */}
            <div>
              <label className="block text-sm text-slate-300 mb-1">Destination Type</label>
              <select
                value={newRoute.destination_kind}
                onChange={(e) =>
                  setNewRoute({
                    ...newRoute,
                    destination_kind: e.target.value as 'page' | 'external',
                  })
                }
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
              >
                <option value="page">Page</option>
                <option value="external">External URL</option>
              </select>
            </div>

            {/* Page Selection or External URL */}
            {newRoute.destination_kind === 'page' ? (
              <div>
                <label className="block text-sm text-slate-300 mb-1">Select Page</label>
                <select
                  value={newRoute.page_id}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      page_id: e.target.value,
                    })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
                >
                  <option value="">-- Select a page --</option>
                  {pages.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div>
                <label className="block text-sm text-slate-300 mb-1">External URL</label>
                <input
                  type="url"
                  value={newRoute.external_url}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      external_url: e.target.value,
                    })
                  }
                  placeholder="https://example.com/block"
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
                />
              </div>
            )}

            {/* Governance Metadata */}
            <div className="border-t border-slate-600 pt-4">
              <p className="text-sm text-slate-300 font-semibold mb-3">Governance Metadata (Optional)</p>

              <div className="space-y-3">
                <input
                  type="text"
                  value={newRoute.ticket}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      ticket: e.target.value,
                    })
                  }
                  placeholder="Ticket ID"
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                />

                <textarea
                  value={newRoute.notes}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      notes: e.target.value,
                    })
                  }
                  placeholder="Notes"
                  rows={2}
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                />

                <input
                  type="date"
                  value={newRoute.expiry}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      expiry: e.target.value,
                    })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                />

                <select
                  value={newRoute.scope}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      scope: e.target.value,
                    })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                >
                  <option value="">-- Scope --</option>
                  <option value="global">Global</option>
                  <option value="tenant">Tenant</option>
                  <option value="team">Team</option>
                </select>

                <select
                  value={newRoute.risk}
                  onChange={(e) =>
                    setNewRoute({
                      ...newRoute,
                      risk: e.target.value,
                    })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none text-sm"
                >
                  <option value="">-- Risk --</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
            </div>

            {/* Buttons */}
            <div className="flex gap-2 pt-4 border-t border-slate-600">
              <button
                onClick={handleSaveRoute}
                disabled={isPending}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50 transition-colors"
              >
                {isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setIsModalOpen(false)}
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
