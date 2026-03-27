import { useState } from "react";
import {
  Shield,
  Plus,
  Pencil,
  Trash2,
  X,
  ChevronDown,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import clsx from "clsx";
import type { Policy, PolicyRule } from "../lib/api";

// Mock data
const mockPolicies: Policy[] = [
  {
    id: "pol-001",
    name: "Block Malicious Domains",
    description: "Block known malware and phishing domains",
    enabled: true,
    action: "deny",
    priority: 1,
    rules: [
      { dimension: "domain", operator: "matches", value: "*.malware.test" },
      { dimension: "domain", operator: "matches", value: "*.phishing.test" },
    ],
    created_at: "2025-01-15T10:00:00Z",
    updated_at: "2025-02-01T14:30:00Z",
  },
  {
    id: "pol-002",
    name: "Allow Internal DNS",
    description: "Allow all DNS traffic to internal resolvers",
    enabled: true,
    action: "allow",
    priority: 2,
    rules: [
      { dimension: "port", operator: "equals", value: "53" },
      { dimension: "ip_cidr", operator: "equals", value: "10.0.0.0/8" },
    ],
    created_at: "2025-01-10T08:00:00Z",
    updated_at: "2025-01-10T08:00:00Z",
  },
  {
    id: "pol-003",
    name: "Restrict SSH Access",
    description: "Only allow SSH from admin group to prod servers",
    enabled: true,
    action: "allow",
    priority: 3,
    rules: [
      { dimension: "port", operator: "equals", value: "22" },
      { dimension: "group", operator: "equals", value: "admins" },
      { dimension: "ip_cidr", operator: "equals", value: "172.16.0.0/12" },
    ],
    created_at: "2025-01-20T12:00:00Z",
    updated_at: "2025-01-25T09:15:00Z",
  },
  {
    id: "pol-004",
    name: "Block Social Media",
    description: "Block social media sites during work hours",
    enabled: false,
    action: "deny",
    priority: 10,
    rules: [
      { dimension: "domain", operator: "contains", value: "facebook.com" },
      { dimension: "domain", operator: "contains", value: "twitter.com" },
      { dimension: "domain", operator: "contains", value: "instagram.com" },
    ],
    created_at: "2025-02-01T16:00:00Z",
    updated_at: "2025-02-01T16:00:00Z",
  },
];

const dimensions: PolicyRule["dimension"][] = [
  "domain",
  "port",
  "protocol",
  "ip_cidr",
  "user",
  "group",
];
const operators: PolicyRule["operator"][] = [
  "equals",
  "contains",
  "matches",
  "in",
];

export default function PolicyManagement() {
  const [policies] = useState<Policy[]>(mockPolicies);
  const [showModal, setShowModal] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
  const [newRules, setNewRules] = useState<PolicyRule[]>([
    { dimension: "domain", operator: "equals", value: "" },
  ]);

  const openCreate = () => {
    setEditingPolicy(null);
    setNewRules([{ dimension: "domain", operator: "equals", value: "" }]);
    setShowModal(true);
  };

  const openEdit = (policy: Policy) => {
    setEditingPolicy(policy);
    setNewRules([...policy.rules]);
    setShowModal(true);
  };

  const addRule = () => {
    setNewRules([
      ...newRules,
      { dimension: "domain", operator: "equals", value: "" },
    ]);
  };

  const removeRule = (index: number) => {
    setNewRules(newRules.filter((_, i) => i !== index));
  };

  const updateRule = (
    index: number,
    field: keyof PolicyRule,
    value: string,
  ) => {
    const updated = [...newRules];
    updated[index] = { ...updated[index], [field]: value };
    setNewRules(updated);
  };

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
                Rules
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
            {policies.map((policy) => (
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
                  <div className="flex flex-wrap gap-1">
                    {policy.rules.slice(0, 2).map((rule, i) => (
                      <span
                        key={i}
                        className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary"
                      >
                        {rule.dimension}: {rule.value}
                      </span>
                    ))}
                    {policy.rules.length > 2 && (
                      <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-muted">
                        +{policy.rules.length - 2} more
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
                      className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                      title="Delete policy"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
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

            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                setShowModal(false);
              }}
            >
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Name
                </label>
                <input
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
                  type="text"
                  defaultValue={editingPolicy?.description ?? ""}
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Action
                  </label>
                  <div className="relative">
                    <select
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
                    Priority
                  </label>
                  <input
                    type="number"
                    min="1"
                    defaultValue={editingPolicy?.priority ?? 10}
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
              </div>

              {/* Rule builder */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-sm font-medium text-text-secondary">
                    Rules
                  </label>
                  <button
                    type="button"
                    onClick={addRule}
                    className="flex items-center gap-1 text-xs text-accent hover:text-accent-hover"
                  >
                    <Plus className="h-3 w-3" /> Add Rule
                  </button>
                </div>
                <div className="space-y-2">
                  {newRules.map((rule, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <select
                          value={rule.dimension}
                          onChange={(e) =>
                            updateRule(
                              index,
                              "dimension",
                              e.target.value,
                            )
                          }
                          className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                        >
                          {dimensions.map((d) => (
                            <option key={d} value={d}>
                              {d}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3 w-3 text-text-muted" />
                      </div>
                      <div className="relative flex-1">
                        <select
                          value={rule.operator}
                          onChange={(e) =>
                            updateRule(
                              index,
                              "operator",
                              e.target.value,
                            )
                          }
                          className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                        >
                          {operators.map((o) => (
                            <option key={o} value={o}>
                              {o}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3 w-3 text-text-muted" />
                      </div>
                      <input
                        type="text"
                        value={rule.value}
                        onChange={(e) =>
                          updateRule(index, "value", e.target.value)
                        }
                        placeholder="Value"
                        className="flex-[2] rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
                      />
                      {newRules.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeRule(index)}
                          className="rounded p-1.5 text-text-muted hover:text-error"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  ))}
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
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover"
                >
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
