import { useState, useEffect } from "react";
import {
  Building2,
  Plus,
  Pencil,
  Trash2,
  X,
  ChevronDown,
  AlertCircle,
} from "lucide-react";
import clsx from "clsx";
import { tenantsApi, type Tenant } from "../lib/api";
import { ScopeGate } from "../lib/auth";

type ModalMode = "create" | "edit";

interface FormState {
  name: string;
  tenant_id: string;
  domain: string;
  spiffe_trust_domain: string;
  is_active: boolean;
  config: string;
}

const emptyForm: FormState = {
  name: "",
  tenant_id: "",
  domain: "",
  spiffe_trust_domain: "",
  is_active: true,
  config: "{}",
};

function tenantToForm(t: Tenant): FormState {
  return {
    name: t.name,
    tenant_id: t.tenant_id,
    domain: t.domain,
    spiffe_trust_domain: t.spiffe_trust_domain,
    is_active: t.is_active,
    config: JSON.stringify(t.config, null, 2),
  };
}

export default function TenantManagement() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>("create");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  useEffect(() => {
    loadTenants();
  }, []);

  async function loadTenants() {
    try {
      setLoading(true);
      setError(null);
      const data = await tenantsApi.list();
      setTenants(data);
    } catch {
      setError("Failed to load tenants. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function openCreate() {
    setForm(emptyForm);
    setModalMode("create");
    setEditingId(null);
    setConfigError(null);
    setShowModal(true);
  }

  function openEdit(tenant: Tenant) {
    setForm(tenantToForm(tenant));
    setModalMode("edit");
    setEditingId(tenant.id);
    setConfigError(null);
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setEditingId(null);
    setConfigError(null);
  }

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let parsedConfig: Record<string, unknown> = {};
    try {
      parsedConfig = JSON.parse(form.config);
    } catch {
      setConfigError("Config must be valid JSON.");
      return;
    }
    setSaving(true);
    try {
      if (modalMode === "create") {
        const created = await tenantsApi.create({
          tenant_id: form.tenant_id,
          name: form.name,
          domain: form.domain,
          spiffe_trust_domain: form.spiffe_trust_domain,
          is_active: form.is_active,
          config: parsedConfig,
        });
        setTenants((prev) => [...prev, created]);
      } else if (editingId) {
        const updated = await tenantsApi.update(editingId, {
          name: form.name,
          domain: form.domain,
          spiffe_trust_domain: form.spiffe_trust_domain,
          is_active: form.is_active,
          config: parsedConfig,
        });
        setTenants((prev) =>
          prev.map((t) => (t.id === editingId ? updated : t)),
        );
      }
      closeModal();
    } catch {
      setError(
        modalMode === "create"
          ? "Failed to create tenant."
          : "Failed to update tenant.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await tenantsApi.delete(id);
      setTenants((prev) => prev.filter((t) => t.id !== id));
      setDeleteConfirmId(null);
    } catch {
      setError("Failed to delete tenant.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Tenants</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage organizational tenants and their SPIFFE trust domains
          </p>
        </div>
        <ScopeGate scope="tenants:admin">
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" />
            Create Tenant
          </button>
        </ScopeGate>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-auto rounded p-0.5 hover:bg-error/20"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Tenant table */}
      <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : tenants.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-secondary">
            <Building2 className="h-10 w-10 text-text-muted" />
            <p className="text-sm">No tenants found.</p>
            <ScopeGate scope="tenants:admin">
              <button
                onClick={openCreate}
                className="text-sm text-accent hover:underline"
              >
                Create your first tenant
              </button>
            </ScopeGate>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-bg-primary/50">
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Tenant ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Domain
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  SPIFFE Trust Domain
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-text-muted">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tenants.map((tenant) => (
                <tr
                  key={tenant.id}
                  className="transition-colors hover:bg-bg-primary/30"
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15">
                        <Building2 className="h-4 w-4 text-accent" />
                      </div>
                      <span className="text-sm font-medium text-text-primary">
                        {tenant.name}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                    {tenant.tenant_id}
                  </td>
                  <td className="px-6 py-4 text-sm text-text-secondary">
                    {tenant.domain || <span className="text-text-muted">—</span>}
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                    {tenant.spiffe_trust_domain || (
                      <span className="text-text-muted">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={clsx(
                        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
                        tenant.is_active
                          ? "bg-success/10 text-success"
                          : "bg-bg-tertiary text-text-muted",
                      )}
                    >
                      {tenant.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <ScopeGate scope="tenants:admin">
                        <button
                          onClick={() => openEdit(tenant)}
                          className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                          title="Edit tenant"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                      </ScopeGate>
                      <ScopeGate scope="tenants:delete">
                        <button
                          onClick={() => setDeleteConfirmId(tenant.id)}
                          className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                          title="Delete tenant"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </ScopeGate>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg rounded-xl border border-border bg-bg-secondary p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                {modalMode === "create" ? "Create Tenant" : "Edit Tenant"}
              </h2>
              <button
                onClick={closeModal}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Name
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setField("name", e.target.value)}
                    required
                    placeholder="Acme Corp"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Tenant ID
                  </label>
                  <input
                    type="text"
                    value={form.tenant_id}
                    onChange={(e) => setField("tenant_id", e.target.value)}
                    required
                    disabled={modalMode === "edit"}
                    placeholder="acme-corp"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Domain
                </label>
                <input
                  type="text"
                  value={form.domain}
                  onChange={(e) => setField("domain", e.target.value)}
                  placeholder="acme.example.com"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  SPIFFE Trust Domain
                </label>
                <input
                  type="text"
                  value={form.spiffe_trust_domain}
                  onChange={(e) =>
                    setField("spiffe_trust_domain", e.target.value)
                  }
                  placeholder="acme.example.com"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Status
                </label>
                <div className="relative">
                  <select
                    value={form.is_active ? "active" : "inactive"}
                    onChange={(e) =>
                      setField("is_active", e.target.value === "active")
                    }
                    className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Config (JSON)
                </label>
                <textarea
                  value={form.config}
                  onChange={(e) => {
                    setField("config", e.target.value);
                    setConfigError(null);
                  }}
                  rows={4}
                  className={clsx(
                    "w-full rounded-lg border bg-bg-primary px-4 py-2.5 font-mono text-xs text-text-primary focus:outline-none focus:ring-1",
                    configError
                      ? "border-error focus:border-error focus:ring-error"
                      : "border-border focus:border-accent focus:ring-accent",
                  )}
                />
                {configError && (
                  <p className="mt-1 text-xs text-error">{configError}</p>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving
                    ? "Saving..."
                    : modalMode === "create"
                      ? "Create Tenant"
                      : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-bg-secondary p-6">
            <h2 className="text-lg font-semibold text-text-primary">
              Delete Tenant?
            </h2>
            <p className="mt-2 text-sm text-text-secondary">
              This action cannot be undone. All associated teams and SPIFFE
              entries will also be affected.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                className="rounded-lg bg-error px-4 py-2 text-sm font-semibold text-white hover:bg-error/80"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
