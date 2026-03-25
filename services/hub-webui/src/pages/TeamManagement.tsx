import { useState, useEffect } from "react";
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  X,
  ChevronDown,
  AlertCircle,
  UserPlus,
  UserMinus,
  ChevronRight,
} from "lucide-react";
import clsx from "clsx";
import { teamsApi, type Team, type TeamMembership } from "../lib/api";
import { useAuth, ScopeGate } from "../lib/auth";

type ModalMode = "create" | "edit";

interface TeamFormState {
  name: string;
  team_id: string;
  description: string;
}

const emptyTeamForm: TeamFormState = {
  name: "",
  team_id: "",
  description: "",
};

interface MemberFormState {
  user_id: string;
  role_in_team: TeamMembership["role_in_team"];
}

const emptyMemberForm: MemberFormState = {
  user_id: "",
  role_in_team: "viewer",
};

// Mock members per team — in production these come from a /teams/:id/members endpoint
type MockMemberMap = Record<string, TeamMembership[]>;
const initialMockMembers: MockMemberMap = {};

export default function TeamManagement() {
  const { user } = useAuth();
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Team modal
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [teamModalMode, setTeamModalMode] = useState<ModalMode>("create");
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [teamForm, setTeamForm] = useState<TeamFormState>(emptyTeamForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Member management
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [membersMap, setMembersMap] =
    useState<MockMemberMap>(initialMockMembers);
  const [showMemberModal, setShowMemberModal] = useState(false);
  const [memberForm, setMemberForm] =
    useState<MemberFormState>(emptyMemberForm);
  const [memberSaving, setMemberSaving] = useState(false);

  useEffect(() => {
    loadTeams();
  }, []);

  async function loadTeams() {
    try {
      setLoading(true);
      setError(null);
      const data = await teamsApi.list(user?.tenant ?? undefined);
      setTeams(data);
    } catch {
      setError("Failed to load teams. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function openCreateTeam() {
    setTeamForm(emptyTeamForm);
    setTeamModalMode("create");
    setEditingTeamId(null);
    setShowTeamModal(true);
  }

  function openEditTeam(team: Team) {
    setTeamForm({
      name: team.name,
      team_id: team.team_id,
      description: team.description,
    });
    setTeamModalMode("edit");
    setEditingTeamId(team.id);
    setShowTeamModal(true);
  }

  function setTeamField<K extends keyof TeamFormState>(
    key: K,
    value: TeamFormState[K],
  ) {
    setTeamForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleTeamSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      if (teamModalMode === "create") {
        const created = await teamsApi.create({
          team_id: teamForm.team_id,
          name: teamForm.name,
          description: teamForm.description,
          tenant_id: user?.tenant ?? "",
        });
        setTeams((prev) => [...prev, created]);
      } else if (editingTeamId) {
        // teams API has no update endpoint in spec; optimistic local update
        setTeams((prev) =>
          prev.map((t) =>
            t.id === editingTeamId
              ? { ...t, name: teamForm.name, description: teamForm.description }
              : t,
          ),
        );
      }
      setShowTeamModal(false);
    } catch {
      setError(
        teamModalMode === "create"
          ? "Failed to create team."
          : "Failed to update team.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteTeam(id: string) {
    try {
      await teamsApi.delete(id);
      setTeams((prev) => prev.filter((t) => t.id !== id));
      if (selectedTeamId === id) setSelectedTeamId(null);
      setDeleteConfirmId(null);
    } catch {
      setError("Failed to delete team.");
    }
  }

  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedTeamId || !memberForm.user_id.trim()) return;
    setMemberSaving(true);
    try {
      await teamsApi.addMember(selectedTeamId, {
        user_id: memberForm.user_id.trim(),
        team_id: selectedTeamId,
        role_in_team: memberForm.role_in_team,
      });
      setMembersMap((prev) => ({
        ...prev,
        [selectedTeamId]: [
          ...(prev[selectedTeamId] ?? []),
          {
            user_id: memberForm.user_id.trim(),
            team_id: selectedTeamId,
            role_in_team: memberForm.role_in_team,
          },
        ],
      }));
      setShowMemberModal(false);
      setMemberForm(emptyMemberForm);
    } catch {
      setError("Failed to add member.");
    } finally {
      setMemberSaving(false);
    }
  }

  async function handleRemoveMember(teamId: string, userId: string) {
    try {
      await teamsApi.removeMember(teamId, userId);
      setMembersMap((prev) => ({
        ...prev,
        [teamId]: (prev[teamId] ?? []).filter((m) => m.user_id !== userId),
      }));
    } catch {
      setError("Failed to remove member.");
    }
  }

  const selectedTeam = teams.find((t) => t.id === selectedTeamId) ?? null;
  const selectedMembers = selectedTeamId
    ? (membersMap[selectedTeamId] ?? [])
    : [];

  const roleColors: Record<TeamMembership["role_in_team"], string> = {
    admin: "bg-accent/10 text-accent",
    maintainer: "bg-info/10 text-info",
    viewer: "bg-bg-tertiary text-text-secondary",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Teams</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage teams and their membership within your tenant
          </p>
        </div>
        <ScopeGate scope="teams:admin">
          <button
            onClick={openCreateTeam}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" />
            Create Team
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Team list */}
        <div className="lg:col-span-1">
          <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              </div>
            ) : teams.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 text-text-secondary">
                <Users className="h-10 w-10 text-text-muted" />
                <p className="text-sm">No teams found.</p>
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {teams.map((team) => (
                  <li key={team.id}>
                    <button
                      onClick={() =>
                        setSelectedTeamId(
                          selectedTeamId === team.id ? null : team.id,
                        )
                      }
                      className={clsx(
                        "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-bg-primary/30",
                        selectedTeamId === team.id && "bg-accent/5",
                      )}
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/15">
                        <Users className="h-4 w-4 text-accent" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-text-primary">
                          {team.name}
                        </p>
                        <p className="truncate text-xs text-text-muted">
                          {team.team_id}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <span className="text-xs text-text-muted">
                          {(membersMap[team.id] ?? []).length}
                        </span>
                        <ChevronRight
                          className={clsx(
                            "h-4 w-4 text-text-muted transition-transform",
                            selectedTeamId === team.id && "rotate-90",
                          )}
                        />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Team detail / member panel */}
        <div className="lg:col-span-2">
          {selectedTeam ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-border bg-bg-secondary p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-text-primary">
                      {selectedTeam.name}
                    </h2>
                    <p className="mt-0.5 font-mono text-xs text-text-muted">
                      {selectedTeam.team_id}
                    </p>
                    {selectedTeam.description && (
                      <p className="mt-2 text-sm text-text-secondary">
                        {selectedTeam.description}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <ScopeGate scope="teams:admin">
                      <button
                        onClick={() => openEditTeam(selectedTeam)}
                        className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                        title="Edit team"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    </ScopeGate>
                    <ScopeGate scope="teams:delete">
                      <button
                        onClick={() => setDeleteConfirmId(selectedTeam.id)}
                        className="rounded p-1.5 text-text-secondary hover:bg-error/10 hover:text-error"
                        title="Delete team"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </ScopeGate>
                  </div>
                </div>
              </div>

              {/* Members */}
              <div className="overflow-hidden rounded-xl border border-border bg-bg-secondary">
                <div className="flex items-center justify-between border-b border-border px-5 py-3">
                  <h3 className="text-sm font-semibold text-text-primary">
                    Members
                  </h3>
                  <ScopeGate scope="teams:admin">
                    <button
                      onClick={() => {
                        setMemberForm(emptyMemberForm);
                        setShowMemberModal(true);
                      }}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                    >
                      <UserPlus className="h-3.5 w-3.5" />
                      Add Member
                    </button>
                  </ScopeGate>
                </div>
                {selectedMembers.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-10 text-text-muted">
                    <Users className="h-8 w-8" />
                    <p className="text-sm">No members yet.</p>
                  </div>
                ) : (
                  <ul className="divide-y divide-border">
                    {selectedMembers.map((member) => (
                      <li
                        key={member.user_id}
                        className="flex items-center justify-between px-5 py-3"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-bg-tertiary text-xs font-semibold text-text-muted">
                            {member.user_id.slice(0, 2).toUpperCase()}
                          </div>
                          <span className="text-sm text-text-primary">
                            {member.user_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span
                            className={clsx(
                              "rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
                              roleColors[member.role_in_team],
                            )}
                          >
                            {member.role_in_team}
                          </span>
                          <ScopeGate scope="teams:admin">
                            <button
                              onClick={() =>
                                handleRemoveMember(
                                  selectedTeam.id,
                                  member.user_id,
                                )
                              }
                              className="rounded p-1 text-text-muted hover:bg-error/10 hover:text-error"
                              title="Remove member"
                            >
                              <UserMinus className="h-3.5 w-3.5" />
                            </button>
                          </ScopeGate>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-64 items-center justify-center rounded-xl border border-border bg-bg-secondary text-text-muted">
              <div className="text-center">
                <Users className="mx-auto mb-2 h-8 w-8" />
                <p className="text-sm">Select a team to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Team Modal */}
      {showTeamModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-bg-secondary p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                {teamModalMode === "create" ? "Create Team" : "Edit Team"}
              </h2>
              <button
                onClick={() => setShowTeamModal(false)}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleTeamSubmit}>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Name
                </label>
                <input
                  type="text"
                  value={teamForm.name}
                  onChange={(e) => setTeamField("name", e.target.value)}
                  required
                  placeholder="Engineering"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Team ID
                </label>
                <input
                  type="text"
                  value={teamForm.team_id}
                  onChange={(e) => setTeamField("team_id", e.target.value)}
                  required
                  disabled={teamModalMode === "edit"}
                  placeholder="engineering"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Description
                </label>
                <textarea
                  value={teamForm.description}
                  onChange={(e) => setTeamField("description", e.target.value)}
                  rows={3}
                  placeholder="Describe this team's purpose"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowTeamModal(false)}
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
                    : teamModalMode === "create"
                      ? "Create Team"
                      : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Member Modal */}
      {showMemberModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-bg-secondary p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-gold">
                Add Member
              </h2>
              <button
                onClick={() => setShowMemberModal(false)}
                className="rounded p-1.5 text-text-secondary hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleAddMember}>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  User ID
                </label>
                <input
                  type="text"
                  value={memberForm.user_id}
                  onChange={(e) =>
                    setMemberForm((prev) => ({
                      ...prev,
                      user_id: e.target.value,
                    }))
                  }
                  required
                  placeholder="usr-001"
                  className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Role
                </label>
                <div className="relative">
                  <select
                    value={memberForm.role_in_team}
                    onChange={(e) =>
                      setMemberForm((prev) => ({
                        ...prev,
                        role_in_team: e.target
                          .value as TeamMembership["role_in_team"],
                      }))
                    }
                    className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="admin">Admin</option>
                    <option value="maintainer">Maintainer</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowMemberModal(false)}
                  className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={memberSaving}
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {memberSaving ? "Adding..." : "Add Member"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Team confirmation */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-bg-secondary p-6">
            <h2 className="text-lg font-semibold text-text-primary">
              Delete Team?
            </h2>
            <p className="mt-2 text-sm text-text-secondary">
              This action cannot be undone. All team memberships will be
              removed.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteTeam(deleteConfirmId)}
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
