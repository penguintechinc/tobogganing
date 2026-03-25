import { useState } from "react";
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  X,
  ShieldCheck,
  Eye,
  Wrench,
  ChevronDown,
} from "lucide-react";
import clsx from "clsx";
import type { User } from "../lib/api";

const mockUsers: User[] = [
  {
    id: "usr-001",
    email: "admin@corp.io",
    name: "Alice Chen",
    role: "admin",
    created_at: "2024-11-01T08:00:00Z",
  },
  {
    id: "usr-002",
    email: "bob@corp.io",
    name: "Bob Martinez",
    role: "maintainer",
    created_at: "2024-12-15T10:00:00Z",
  },
  {
    id: "usr-003",
    email: "carol@corp.io",
    name: "Carol Williams",
    role: "viewer",
    created_at: "2025-01-05T14:00:00Z",
  },
  {
    id: "usr-004",
    email: "dave@corp.io",
    name: "Dave Johnson",
    role: "maintainer",
    created_at: "2025-01-20T09:00:00Z",
  },
];

const roleConfig = {
  admin: {
    icon: ShieldCheck,
    label: "Admin",
    description: "Full access to all features",
    color: "text-accent bg-accent/10",
  },
  maintainer: {
    icon: Wrench,
    label: "Maintainer",
    description: "Read/write access, no user management",
    color: "text-info bg-info/10",
  },
  viewer: {
    icon: Eye,
    label: "Viewer",
    description: "Read-only access",
    color: "text-text-secondary bg-bg-tertiary",
  },
};

export default function UserManagement() {
  const [users] = useState(mockUsers);
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const openCreate = () => {
    setEditingUser(null);
    setShowModal(true);
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    setShowModal(true);
  };

  const roleCounts = {
    admin: users.filter((u) => u.role === "admin").length,
    maintainer: users.filter((u) => u.role === "maintainer").length,
    viewer: users.filter((u) => u.role === "viewer").length,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Users</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage user accounts and role-based access control
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" />
          Add User
        </button>
      </div>

      {/* Role summary */}
      <div className="grid grid-cols-3 gap-3">
        {(Object.entries(roleConfig) as [keyof typeof roleConfig, typeof roleConfig.admin][]).map(
          ([role, config]) => (
            <div
              key={role}
              className="rounded-xl border border-border bg-bg-secondary p-4"
            >
              <div className="flex items-center gap-2">
                <config.icon className={clsx("h-5 w-5", config.color.split(" ")[0])} />
                <span className="text-sm font-medium text-text-primary">
                  {config.label}
                </span>
              </div>
              <p className="mt-1 text-2xl font-bold text-text-gold">
                {roleCounts[role]}
              </p>
              <p className="mt-0.5 text-xs text-text-muted">
                {config.description}
              </p>
            </div>
          ),
        )}
      </div>

      {/* User table */}
      <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-bg-primary/50">
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                User
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Role
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-text-muted">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((user) => {
              const config = roleConfig[user.role];
              return (
                <tr
                  key={user.id}
                  className="transition-colors hover:bg-bg-primary/30"
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-text-gold">
                        {user.name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-text-primary">
                          {user.name}
                        </p>
                        <p className="text-xs text-text-muted">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                        config.color,
                      )}
                    >
                      <config.icon className="h-3 w-3" />
                      {config.label}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-text-secondary">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openEdit(user)}
                        className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                        title="Edit user"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                        title="Delete user"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-bg-secondary p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                {editingUser ? "Edit User" : "Add User"}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary"
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
                  defaultValue={editingUser?.name ?? ""}
                  required
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Email
                </label>
                <input
                  type="email"
                  defaultValue={editingUser?.email ?? ""}
                  required
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              {!editingUser && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                    Password
                  </label>
                  <input
                    type="password"
                    required
                    className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Role
                </label>
                <div className="relative">
                  <select
                    defaultValue={editingUser?.role ?? "viewer"}
                    className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="admin">Admin - Full access</option>
                    <option value="maintainer">
                      Maintainer - Read/write access
                    </option>
                    <option value="viewer">Viewer - Read-only access</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
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
                  {editingUser ? "Save Changes" : "Create User"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
