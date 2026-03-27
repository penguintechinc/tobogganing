import { useState } from "react";
import {
  ScrollText,
  Search,
  Filter,
  Download,
  Shield,
  LogIn,
  Settings,
  Server,
  CheckCircle,
  XCircle,
  ChevronDown,
} from "lucide-react";
import clsx from "clsx";
import type { AuditLogEntry } from "../lib/api";

const mockAuditLogs: AuditLogEntry[] = [
  {
    id: "log-001",
    timestamp: "2025-02-08T12:05:00Z",
    event_type: "policy_decision",
    actor: "system",
    action: "evaluate",
    target: "Block Malicious Domains",
    details: "Denied DNS request to evil.malware.test from client-047",
    result: "success",
  },
  {
    id: "log-002",
    timestamp: "2025-02-08T12:02:00Z",
    event_type: "auth",
    actor: "admin@corp.io",
    action: "login",
    target: "hub-webui",
    details: "Successful login from 10.0.1.15",
    result: "success",
  },
  {
    id: "log-003",
    timestamp: "2025-02-08T11:58:00Z",
    event_type: "admin_action",
    actor: "admin@corp.io",
    action: "update",
    target: "Policy: Allow Internal DNS",
    details: "Updated priority from 5 to 2",
    result: "success",
  },
  {
    id: "log-004",
    timestamp: "2025-02-08T11:45:00Z",
    event_type: "auth",
    actor: "unknown@external.com",
    action: "login",
    target: "hub-webui",
    details: "Failed login attempt from 203.0.113.50",
    result: "failure",
  },
  {
    id: "log-005",
    timestamp: "2025-02-08T11:30:00Z",
    event_type: "system",
    actor: "system",
    action: "health_check",
    target: "hub-eu-west-1",
    details: "Health check detected degraded performance, latency 450ms",
    result: "failure",
  },
  {
    id: "log-006",
    timestamp: "2025-02-08T11:15:00Z",
    event_type: "admin_action",
    actor: "bob@corp.io",
    action: "create",
    target: "Client: staging-api-gateway",
    details: "Registered new client with pending status",
    result: "success",
  },
  {
    id: "log-007",
    timestamp: "2025-02-08T11:00:00Z",
    event_type: "policy_decision",
    actor: "system",
    action: "evaluate",
    target: "Restrict SSH Access",
    details: "Allowed SSH from admin group user bob@corp.io to 172.16.1.50",
    result: "success",
  },
  {
    id: "log-008",
    timestamp: "2025-02-08T10:45:00Z",
    event_type: "admin_action",
    actor: "admin@corp.io",
    action: "create",
    target: "User: dave@corp.io",
    details: "Created new user with maintainer role",
    result: "success",
  },
];

const eventTypeConfig = {
  policy_decision: {
    icon: Shield,
    label: "Policy Decision",
    color: "text-info",
  },
  auth: {
    icon: LogIn,
    label: "Authentication",
    color: "text-accent",
  },
  admin_action: {
    icon: Settings,
    label: "Admin Action",
    color: "text-text-gold",
  },
  system: {
    icon: Server,
    label: "System",
    color: "text-text-secondary",
  },
};

export default function AuditLogs() {
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [resultFilter, setResultFilter] = useState<string>("all");

  const filteredLogs = mockAuditLogs.filter((log) => {
    const matchesSearch =
      log.action.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.actor.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.target.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.details.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType =
      typeFilter === "all" || log.event_type === typeFilter;
    const matchesResult =
      resultFilter === "all" || log.result === resultFilter;
    return matchesSearch && matchesType && matchesResult;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Audit Logs</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Review policy decisions, authentication events, and admin actions
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-tertiary hover:text-text-primary">
          <Download className="h-4 w-4" />
          Export
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-secondary py-2 pl-10 pr-4 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="appearance-none rounded-lg border border-border bg-bg-secondary py-2 pl-9 pr-8 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            <option value="all">All Types</option>
            <option value="policy_decision">Policy Decisions</option>
            <option value="auth">Authentication</option>
            <option value="admin_action">Admin Actions</option>
            <option value="system">System</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-text-muted" />
        </div>
        <div className="relative">
          <select
            value={resultFilter}
            onChange={(e) => setResultFilter(e.target.value)}
            className="appearance-none rounded-lg border border-border bg-bg-secondary px-4 py-2 pr-8 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            <option value="all">All Results</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-text-muted" />
        </div>
      </div>

      {/* Log entries */}
      <div className="space-y-2">
        {filteredLogs.map((log) => {
          const config = eventTypeConfig[log.event_type];
          return (
            <div
              key={log.id}
              className="rounded-xl border border-border bg-bg-secondary p-4 transition-colors hover:border-border-light"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-lg bg-bg-primary p-2">
                  <config.icon className={clsx("h-4 w-4", config.color)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={clsx(
                        "text-xs font-medium",
                        config.color,
                      )}
                    >
                      {config.label}
                    </span>
                    <span className="text-xs text-text-muted">
                      {new Date(log.timestamp).toLocaleString()}
                    </span>
                    {log.result === "success" ? (
                      <CheckCircle className="h-3.5 w-3.5 text-success" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-error" />
                    )}
                  </div>
                  <p className="mt-1 text-sm text-text-primary">
                    {log.details}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                      actor: {log.actor}
                    </span>
                    <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                      action: {log.action}
                    </span>
                    <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                      target: {log.target}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        {filteredLogs.length === 0 && (
          <div className="rounded-xl border border-border bg-bg-secondary p-12 text-center">
            <ScrollText className="mx-auto mb-3 h-8 w-8 text-text-muted" />
            <p className="text-text-secondary">No logs match your filters</p>
          </div>
        )}
      </div>
    </div>
  );
}
