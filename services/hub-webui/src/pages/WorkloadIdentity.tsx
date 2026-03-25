import { useState, useEffect } from "react";
import {
  Fingerprint,
  Plus,
  Trash2,
  X,
  AlertCircle,
  PlusCircle,
  MinusCircle,
} from "lucide-react";
import clsx from "clsx";
import { spiffeApi, type SpiffeEntry } from "../lib/api";
import { useAuth, ScopeGate } from "../lib/auth";

interface SelectorPair {
  key: string;
  value: string;
}

interface CreateFormState {
  trust_domain: string;
  cluster: string;
  namespace: string;
  service: string;
  parent_id: string;
  selectors: SelectorPair[];
  ttl: string;
  dns_names: string;
}

const emptyForm: CreateFormState = {
  trust_domain: "",
  cluster: "",
  namespace: "",
  service: "",
  parent_id: "",
  selectors: [{ key: "", value: "" }],
  ttl: "3600",
  dns_names: "",
};

function buildSpiffeId(form: CreateFormState): string {
  const td = form.trust_domain || "<trust-domain>";
  const parts = [
    form.cluster && `cluster/${form.cluster}`,
    form.namespace && `ns/${form.namespace}`,
    form.service && `sa/${form.service}`,
  ].filter(Boolean);
  return `spiffe://${td}/${parts.join("/")}`;
}

const statusConfig = {
  active: { label: "Active", classes: "bg-success/10 text-success" },
  pending: { label: "Pending", classes: "bg-warning/10 text-warning" },
  expired: { label: "Expired", classes: "bg-error/10 text-error" },
} as const;

export default function WorkloadIdentity() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<SpiffeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CreateFormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  useEffect(() => {
    loadEntries();
  }, []);

  // Pre-populate trust domain from user tenant when modal opens
  useEffect(() => {
    if (showModal && user?.tenant) {
      setForm((prev) => ({ ...prev, trust_domain: user.tenant }));
    }
  }, [showModal, user?.tenant]);

  async function loadEntries() {
    try {
      setLoading(true);
      setError(null);
      const data = await spiffeApi.list();
      setEntries(data);
    } catch {
      setError("Failed to load SPIFFE entries. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function openCreate() {
    setForm({
      ...emptyForm,
      trust_domain: user?.tenant ?? "",
    });
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
  }

  function setField<K extends keyof CreateFormState>(
    key: K,
    value: CreateFormState[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function addSelector() {
    setForm((prev) => ({
      ...prev,
      selectors: [...prev.selectors, { key: "", value: "" }],
    }));
  }

  function removeSelector(index: number) {
    setForm((prev) => ({
      ...prev,
      selectors: prev.selectors.filter((_, i) => i !== index),
    }));
  }

  function updateSelector(
    index: number,
    field: "key" | "value",
    value: string,
  ) {
    setForm((prev) => ({
      ...prev,
      selectors: prev.selectors.map((s, i) =>
        i === index ? { ...s, [field]: value } : s,
      ),
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const spiffe_id = buildSpiffeId(form);
    const selectorRecord = form.selectors
      .filter((s) => s.key.trim())
      .reduce<Record<string, string>>((acc, s) => {
        acc[s.key.trim()] = s.value.trim();
        return acc;
      }, {});
    const dns_names = form.dns_names
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const ttl = parseInt(form.ttl, 10) || 3600;

    setSaving(true);
    try {
      const created = await spiffeApi.create({
        spiffe_id,
        tenant_id: user?.tenant ?? "",
        parent_id: form.parent_id,
        selectors: selectorRecord,
        ttl,
        dns_names,
      });
      setEntries((prev) => [...prev, created]);
      closeModal();
    } catch {
      setError("Failed to create SPIFFE entry.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await spiffeApi.delete(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
      setDeleteConfirmId(null);
    } catch {
      setError("Failed to delete SPIFFE entry.");
    }
  }

  const spiffePreview = buildSpiffeId(form);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">
            Workload Identity
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage SPIFFE/SPIRE workload identity entries
          </p>
        </div>
        <ScopeGate scope="spiffe:admin">
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" />
            Create Entry
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

      {/* Entries table */}
      <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-secondary">
            <Fingerprint className="h-10 w-10 text-text-muted" />
            <p className="text-sm">No SPIFFE entries found.</p>
            <ScopeGate scope="spiffe:admin">
              <button
                onClick={openCreate}
                className="text-sm text-accent hover:underline"
              >
                Create your first entry
              </button>
            </ScopeGate>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px]">
              <thead>
                <tr className="border-b border-border bg-bg-primary/50">
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                    SPIFFE ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                    Tenant
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                    Parent ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                    TTL
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                    DNS Names
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
                {entries.map((entry) => {
                  const sc = statusConfig[entry.status];
                  return (
                    <tr
                      key={entry.id}
                      className="transition-colors hover:bg-bg-primary/30"
                    >
                      <td className="max-w-xs px-6 py-4">
                        <div className="flex items-center gap-2">
                          <Fingerprint className="h-4 w-4 shrink-0 text-text-muted" />
                          <span
                            className="truncate font-mono text-xs text-text-primary"
                            title={entry.spiffe_id}
                          >
                            {entry.spiffe_id}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                        {entry.tenant_id}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                        {entry.parent_id || (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm text-text-secondary">
                        {entry.ttl}s
                      </td>
                      <td className="px-6 py-4">
                        {entry.dns_names.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {entry.dns_names.slice(0, 2).map((d) => (
                              <span
                                key={d}
                                className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-text-secondary"
                              >
                                {d}
                              </span>
                            ))}
                            {entry.dns_names.length > 2 && (
                              <span className="text-xs text-text-muted">
                                +{entry.dns_names.length - 2}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={clsx(
                            "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
                            sc.classes,
                          )}
                        >
                          {sc.label}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <ScopeGate scope="spiffe:delete">
                          <button
                            onClick={() => setDeleteConfirmId(entry.id)}
                            className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                            title="Delete entry"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </ScopeGate>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Entry Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-bg-secondary p-6 max-h-[90vh]">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                Create SPIFFE Entry
              </h2>
              <button
                onClick={closeModal}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              {/* SPIFFE ID preview */}
              <div className="rounded-lg bg-bg-primary px-4 py-3">
                <p className="mb-1 text-xs font-medium text-text-muted">
                  SPIFFE ID Preview
                </p>
                <p className="break-all font-mono text-xs text-accent">
                  {spiffePreview}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Trust Domain
                  </label>
                  <input
                    type="text"
                    value={form.trust_domain}
                    onChange={(e) => setField("trust_domain", e.target.value)}
                    required
                    placeholder="example.com"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Cluster
                  </label>
                  <input
                    type="text"
                    value={form.cluster}
                    onChange={(e) => setField("cluster", e.target.value)}
                    placeholder="prod-east"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Namespace
                  </label>
                  <input
                    type="text"
                    value={form.namespace}
                    onChange={(e) => setField("namespace", e.target.value)}
                    placeholder="default"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Service Account
                  </label>
                  <input
                    type="text"
                    value={form.service}
                    onChange={(e) => setField("service", e.target.value)}
                    placeholder="my-service"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Parent ID
                </label>
                <input
                  type="text"
                  value={form.parent_id}
                  onChange={(e) => setField("parent_id", e.target.value)}
                  placeholder="spiffe://example.com/agent/node1"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              {/* Selectors */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-sm font-medium text-text-secondary">
                    Selectors
                  </label>
                  <button
                    type="button"
                    onClick={addSelector}
                    className="flex items-center gap-1 text-xs text-accent hover:text-accent-hover"
                  >
                    <PlusCircle className="h-3.5 w-3.5" />
                    Add
                  </button>
                </div>
                <div className="space-y-2">
                  {form.selectors.map((selector, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={selector.key}
                        onChange={(e) =>
                          updateSelector(idx, "key", e.target.value)
                        }
                        placeholder="k8s:ns"
                        className="flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                      <span className="text-text-muted">:</span>
                      <input
                        type="text"
                        value={selector.value}
                        onChange={(e) =>
                          updateSelector(idx, "value", e.target.value)
                        }
                        placeholder="default"
                        className="flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                      <button
                        type="button"
                        onClick={() => removeSelector(idx)}
                        disabled={form.selectors.length === 1}
                        className="rounded p-1 text-text-muted hover:bg-error/10 hover:text-error disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <MinusCircle className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    TTL (seconds)
                  </label>
                  <input
                    type="number"
                    value={form.ttl}
                    onChange={(e) => setField("ttl", e.target.value)}
                    min="60"
                    max="86400"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    DNS Names
                  </label>
                  <input
                    type="text"
                    value={form.dns_names}
                    onChange={(e) => setField("dns_names", e.target.value)}
                    placeholder="svc.ns.svc.cluster.local"
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <p className="mt-1 text-xs text-text-muted">
                    Comma-separated
                  </p>
                </div>
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
                  {saving ? "Creating..." : "Create Entry"}
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
              Delete SPIFFE Entry?
            </h2>
            <p className="mt-2 text-sm text-text-secondary">
              This will immediately revoke the workload identity. Running
              workloads may lose connectivity.
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
