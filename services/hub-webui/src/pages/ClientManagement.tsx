import { useState } from "react";
import { Monitor, Search, RefreshCw, Wifi, WifiOff, Clock } from "lucide-react";
import clsx from "clsx";
import type { Client } from "../lib/api";

const mockClients: Client[] = [
  {
    id: "cli-001",
    name: "dev-laptop-alice",
    hostname: "alice-mbp.local",
    status: "connected",
    hub_ids: ["hub-us-east-1", "hub-us-west-2"],
    ip_address: "10.0.1.15",
    last_seen: "2025-02-08T12:00:00Z",
    version: "1.4.2",
  },
  {
    id: "cli-002",
    name: "server-prod-web01",
    hostname: "web01.prod.internal",
    status: "connected",
    hub_ids: ["hub-us-east-1"],
    ip_address: "10.0.2.50",
    last_seen: "2025-02-08T12:00:00Z",
    version: "1.4.2",
  },
  {
    id: "cli-003",
    name: "dev-laptop-bob",
    hostname: "bob-thinkpad.local",
    status: "disconnected",
    hub_ids: ["hub-eu-west-1"],
    ip_address: "10.0.1.22",
    last_seen: "2025-02-07T18:30:00Z",
    version: "1.4.1",
  },
  {
    id: "cli-004",
    name: "iot-sensor-floor3",
    hostname: "sensor-f3-01.iot",
    status: "connected",
    hub_ids: ["hub-us-east-1", "hub-us-west-2", "hub-eu-west-1"],
    ip_address: "10.0.5.101",
    last_seen: "2025-02-08T11:59:00Z",
    version: "1.3.8",
  },
  {
    id: "cli-005",
    name: "staging-api-gateway",
    hostname: "api-gw.staging.internal",
    status: "pending",
    hub_ids: [],
    ip_address: "10.0.3.10",
    last_seen: "2025-02-08T10:00:00Z",
    version: "1.4.2",
  },
];

export default function ClientManagement() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredClients = mockClients.filter((client) => {
    const matchesSearch =
      client.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      client.hostname.toLowerCase().includes(searchQuery.toLowerCase()) ||
      client.ip_address.includes(searchQuery);
    const matchesStatus =
      statusFilter === "all" || client.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const statusCounts = {
    all: mockClients.length,
    connected: mockClients.filter((c) => c.status === "connected").length,
    disconnected: mockClients.filter((c) => c.status === "disconnected").length,
    pending: mockClients.filter((c) => c.status === "pending").length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-gold">Clients</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Manage connected clients and their hub assignments
        </p>
      </div>

      {/* Status summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(
          [
            { key: "all", label: "Total", icon: Monitor },
            { key: "connected", label: "Connected", icon: Wifi },
            { key: "disconnected", label: "Disconnected", icon: WifiOff },
            { key: "pending", label: "Pending", icon: Clock },
          ] as const
        ).map((item) => (
          <button
            key={item.key}
            onClick={() => setStatusFilter(item.key)}
            className={clsx(
              "rounded-xl border p-4 text-left transition-colors",
              statusFilter === item.key
                ? "border-accent bg-accent/10"
                : "border-border bg-bg-secondary hover:border-border-light",
            )}
          >
            <item.icon
              className={clsx(
                "mb-2 h-5 w-5",
                statusFilter === item.key
                  ? "text-accent"
                  : "text-text-muted",
              )}
            />
            <p className="text-2xl font-bold text-text-primary">
              {statusCounts[item.key]}
            </p>
            <p className="text-xs text-text-muted">{item.label}</p>
          </button>
        ))}
      </div>

      {/* Search and filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search by name, hostname, or IP..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-secondary py-2 pl-10 pr-4 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <button className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text-secondary hover:bg-bg-tertiary">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Client cards */}
      <div className="space-y-3">
        {filteredClients.map((client) => (
          <ClientCard key={client.id} client={client} />
        ))}
        {filteredClients.length === 0 && (
          <div className="rounded-xl border border-border bg-bg-secondary p-12 text-center">
            <Monitor className="mx-auto mb-3 h-8 w-8 text-text-muted" />
            <p className="text-text-secondary">No clients match your search</p>
          </div>
        )}
      </div>
    </div>
  );
}

function ClientCard({ client }: { client: Client }) {
  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-5 transition-colors hover:border-border-light">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div
            className={clsx(
              "mt-1 rounded-lg p-2",
              client.status === "connected" && "bg-success/10",
              client.status === "disconnected" && "bg-error/10",
              client.status === "pending" && "bg-warning/10",
            )}
          >
            <Monitor
              className={clsx(
                "h-5 w-5",
                client.status === "connected" && "text-success",
                client.status === "disconnected" && "text-error",
                client.status === "pending" && "text-warning",
              )}
            />
          </div>
          <div>
            <h3 className="text-sm font-medium text-text-primary">
              {client.name}
            </h3>
            <p className="mt-0.5 text-xs text-text-muted">{client.hostname}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                {client.ip_address}
              </span>
              <span className="rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                v{client.version}
              </span>
            </div>
          </div>
        </div>
        <div className="text-right">
          <span
            className={clsx(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
              client.status === "connected" &&
                "bg-success/10 text-success",
              client.status === "disconnected" &&
                "bg-error/10 text-error",
              client.status === "pending" &&
                "bg-warning/10 text-warning",
            )}
          >
            <span
              className={clsx(
                "h-1.5 w-1.5 rounded-full",
                client.status === "connected" && "bg-success",
                client.status === "disconnected" && "bg-error",
                client.status === "pending" && "bg-warning",
              )}
            />
            {client.status}
          </span>
        </div>
      </div>

      {/* Hub assignments */}
      {client.hub_ids.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="mb-1.5 text-xs font-medium text-text-muted">
            Hub Assignments
          </p>
          <div className="flex flex-wrap gap-1.5">
            {client.hub_ids.map((hubId) => (
              <span
                key={hubId}
                className="rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-text-gold"
              >
                {hubId.replace("hub-", "")}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
