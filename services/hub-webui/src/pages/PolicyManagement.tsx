import { useCallback, useEffect, useRef, useState } from "react";
import {
  Shield,
  Plus,
  Pencil,
  Trash2,
  X,
  ChevronDown,
  ToggleLeft,
  ToggleRight,
  Loader2,
  Globe,
  Network,
} from "lucide-react";
import clsx from "clsx";
import { policiesApi } from "../lib/api";
import type { Policy, PolicyScope } from "../lib/api";

const SCOPE_LABELS: Record<PolicyScope, string> = {
  wireguard: "WireGuard Clients",
  k8s: "Kubernetes Services",
  both: "Both",
};

/** Summarise the active dimensions for a policy as compact chips. */
function dimensionChips(policy: Policy) {
  const chips: { label: string; value: string }[] = [];
  if (policy.domains?.length)
    chips.push({ label: "domain", value: policy.domains.join(", ") });
  if (policy.ports?.length)
    chips.push({ label: "port", value: policy.ports.join(", ") });
  if (policy.src_cidrs?.length)
    chips.push({ label: "src", value: policy.src_cidrs.join(", ") });
  if (policy.dst_cidrs?.length)
    chips.push({ label: "dst", value: policy.dst_cidrs.join(", ") });
  if (policy.users?.length)
    chips.push({ label: "user", value: policy.users.join(", ") });
  if (policy.groups?.length)
    chips.push({ label: "group", value: policy.groups.join(", ") });
  return chips;
}

const EMPTY_FORM: Omit<Policy, "id" | "created_at" | "updated_at"> = {
  name: "",
  description: "",
  action: "allow",
  priority: 100,
  scope: "both",
  direction: "both",
  domains: [],
  ports: [],
  protocol: "any",
  src_cidrs: [],
  dst_cidrs: [],
  users: [],
  groups: [],
  identity_provider: "local",
  enabled: true,
};

export default function PolicyManagement() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
  const [saving, setSaving] = useState(false);

  // Form refs for uncontrolled inputs (better perf for simple text fields)
  const nameRef = useRef<HTMLInputElement>(null);
  const descRef = useRef<HTMLInputElement>(null);
  const priorityRef = useRef<HTMLInputElement>(null);
  const domainsRef = useRef<HTMLInputElement>(null);
  const portsRef = useRef<HTMLInputElement>(null);
  const srcCidrsRef = useRef<HTMLInputElement>(null);
  const dstCidrsRef = useRef<HTMLInputElement>(null);
  const usersRef = useRef<HTMLInputElement>(null);
  const groupsRef = useRef<HTMLInputElement>(null);
  const actionRef = useRef<HTMLSelectElement>(null);
  const scopeRef = useRef<HTMLSelectElement>(null);
  const directionRef = useRef<HTMLSelectElement>(null);
  const protocolRef = useRef<HTMLSelectElement>(null);

  const fetchPolicies = useCallback(async () => {
    try {
      setError(null);
      const data = await policiesApi.list();
      setPolicies(data);
    } catch (err) {
      setError("Failed to load policies");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPolicies();
  }, [fetchPolicies]);

  const openCreate = () => {
    setEditingPolicy(null);
    setShowModal(true);
  };

  const openEdit = (policy: Policy) => {
    setEditingPolicy(policy);
    setShowModal(true);
  };

  const handleDelete = async (policy: Policy) => {
    if (!confirm(`Delete policy "${policy.name}"?`)) return;
    try {
      await policiesApi.delete(policy.id);
      await fetchPolicies();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  /** Split a comma-separated input value into a string array, filtering blanks. */
  const splitField = (ref: React.RefObject<HTMLInputElement | null>) =>
    (ref.current?.value ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: nameRef.current?.value ?? "",
        description: descRef.current?.value ?? "",
        action: (actionRef.current?.value ?? "allow") as "allow" | "deny",
        priority: Number(priorityRef.current?.value ?? 100),
        scope: (scopeRef.current?.value ?? "both") as PolicyScope,
        direction: (directionRef.current?.value ?? "both") as
          | "inbound"
          | "outbound"
          | "both",
        protocol: (protocolRef.current?.value ?? "any") as
          | "tcp"
          | "udp"
          | "icmp"
          | "any",
        domains: splitField(domainsRef),
        ports: splitField(portsRef),
        src_cidrs: splitField(srcCidrsRef),
        dst_cidrs: splitField(dstCidrsRef),
        users: splitField(usersRef),
        groups: splitField(groupsRef),
        identity_provider: "local",
        enabled: true,
      };

      if (editingPolicy) {
        await policiesApi.update(editingPolicy.id, payload);
      } else {
        await policiesApi.create(payload);
      }
      setShowModal(false);
      await fetchPolicies();
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Policies</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage traffic routing and access control policies
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" />
          Create Policy
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      {/* Policy table */}
      <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-bg-primary/50">
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Policy
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Action
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Scope
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Dimensions
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Priority
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
            {policies.map((policy) => {
              const chips = dimensionChips(policy);
              return (
                <tr
                  key={policy.id}
                  className="transition-colors hover:bg-bg-primary/30"
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Shield
                        className={clsx(
                          "h-5 w-5",
                          policy.action === "deny"
                            ? "text-error"
                            : "text-success",
                        )}
                      />
                      <div>
                        <p className="text-sm font-medium text-text-primary">
                          {policy.name}
                        </p>
                        <p className="text-xs text-text-muted">
                          {policy.description}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={clsx(
                        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium",
                        policy.action === "deny"
                          ? "bg-error/10 text-error"
                          : "bg-success/10 text-success",
                      )}
                    >
                      {policy.action}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
                      {policy.scope === "k8s" ? (
                        <Network className="h-3 w-3" />
                      ) : (
                        <Globe className="h-3 w-3" />
                      )}
                      {SCOPE_LABELS[policy.scope]}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {chips.slice(0, 2).map((chip, i) => (
                        <span
                          key={i}
                          className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary"
                        >
                          {chip.label}: {chip.value}
                        </span>
                      ))}
                      {chips.length > 2 && (
                        <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-muted">
                          +{chips.length - 2} more
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-text-secondary">
                    {policy.priority}
                  </td>
                  <td className="px-6 py-4">
                    {policy.enabled ? (
                      <span className="flex items-center gap-1.5 text-xs text-success">
                        <ToggleRight className="h-4 w-4" /> Enabled
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-xs text-text-muted">
                        <ToggleLeft className="h-4 w-4" /> Disabled
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openEdit(policy)}
                        className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                        title="Edit policy"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(policy)}
                        className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                        title="Delete policy"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {policies.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-6 py-12 text-center text-sm text-text-muted"
                >
                  No policies configured yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-border bg-bg-secondary p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                {editingPolicy ? "Edit Policy" : "Create Policy"}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Name
                </label>
                <input
                  ref={nameRef}
                  type="text"
                  defaultValue={editingPolicy?.name ?? ""}
                  required
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Description
                </label>
                <input
                  ref={descRef}
                  type="text"
                  defaultValue={editingPolicy?.description ?? ""}
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Action
                  </label>
                  <div className="relative">
                    <select
                      ref={actionRef}
                      defaultValue={editingPolicy?.action ?? "allow"}
                      className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                    >
                      <option value="allow">Allow</option>
                      <option value="deny">Deny</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Scope
                  </label>
                  <div className="relative">
                    <select
                      ref={scopeRef}
                      defaultValue={editingPolicy?.scope ?? "both"}
                      className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                    >
                      <option value="both">Both</option>
                      <option value="wireguard">WireGuard Clients</option>
                      <option value="k8s">Kubernetes Services</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Priority
                  </label>
                  <input
                    ref={priorityRef}
                    type="number"
                    min="1"
                    defaultValue={editingPolicy?.priority ?? 100}
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Direction
                  </label>
                  <div className="relative">
                    <select
                      ref={directionRef}
                      defaultValue={editingPolicy?.direction ?? "both"}
                      className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                    >
                      <option value="both">Both</option>
                      <option value="inbound">Inbound</option>
                      <option value="outbound">Outbound</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Protocol
                  </label>
                  <div className="relative">
                    <select
                      ref={protocolRef}
                      defaultValue={editingPolicy?.protocol ?? "any"}
                      className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                    >
                      <option value="any">Any</option>
                      <option value="tcp">TCP</option>
                      <option value="udp">UDP</option>
                      <option value="icmp">ICMP</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                  </div>
                </div>
              </div>

              {/* Dimension fields — comma-separated */}
              <div className="space-y-3">
                <p className="text-sm font-medium text-text-secondary">
                  Match Dimensions{" "}
                  <span className="font-normal text-text-muted">
                    (comma-separated)
                  </span>
                </p>
                <div>
                  <label className="mb-1 block text-xs text-text-muted">
                    Domains
                  </label>
                  <input
                    ref={domainsRef}
                    type="text"
                    placeholder="*.example.com, app.internal"
                    defaultValue={editingPolicy?.domains?.join(", ") ?? ""}
                    className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs text-text-muted">
                      Ports
                    </label>
                    <input
                      ref={portsRef}
                      type="text"
                      placeholder="443, 8000-9000"
                      defaultValue={editingPolicy?.ports?.join(", ") ?? ""}
                      className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-text-muted">
                      Source CIDRs
                    </label>
                    <input
                      ref={srcCidrsRef}
                      type="text"
                      placeholder="10.0.0.0/8, 172.16.0.0/12"
                      defaultValue={
                        editingPolicy?.src_cidrs?.join(", ") ?? ""
                      }
                      className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs text-text-muted">
                      Destination CIDRs
                    </label>
                    <input
                      ref={dstCidrsRef}
                      type="text"
                      placeholder="192.168.1.0/24"
                      defaultValue={
                        editingPolicy?.dst_cidrs?.join(", ") ?? ""
                      }
                      className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-text-muted">
                      Groups
                    </label>
                    <input
                      ref={groupsRef}
                      type="text"
                      placeholder="admins, developers"
                      defaultValue={editingPolicy?.groups?.join(", ") ?? ""}
                      className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-text-muted">
                    Users
                  </label>
                  <input
                    ref={usersRef}
                    type="text"
                    placeholder="user-id-1, user-id-2"
                    defaultValue={editingPolicy?.users?.join(", ") ?? ""}
                    className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover disabled:opacity-50"
                >
                  {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editingPolicy ? "Save Changes" : "Create Policy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
