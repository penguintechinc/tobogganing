import { Server, Plus, Activity, Clock, Users, Gauge } from "lucide-react";
import clsx from "clsx";
import type { Hub } from "../lib/api";

const mockHubs: Hub[] = [
  {
    id: "hub-us-east-1",
    name: "US East (Virginia)",
    endpoint: "hub-east.tobogganing.io:443",
    status: "healthy",
    connected_clients: 45,
    capacity: 100,
    uptime_seconds: 864000,
    version: "2.0.0",
  },
  {
    id: "hub-us-west-2",
    name: "US West (Oregon)",
    endpoint: "hub-west.tobogganing.io:443",
    status: "healthy",
    connected_clients: 38,
    capacity: 100,
    uptime_seconds: 720000,
    version: "2.0.0",
  },
  {
    id: "hub-eu-west-1",
    name: "EU West (Ireland)",
    endpoint: "hub-eu.tobogganing.io:443",
    status: "degraded",
    connected_clients: 29,
    capacity: 50,
    uptime_seconds: 432000,
    version: "1.9.8",
  },
  {
    id: "hub-ap-south-1",
    name: "AP South (Mumbai)",
    endpoint: "hub-ap.tobogganing.io:443",
    status: "healthy",
    connected_clients: 0,
    capacity: 50,
    uptime_seconds: 86400,
    version: "2.0.0",
  },
];

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return `${days}d ${hours}h`;
  return `${hours}h`;
}

export default function HubManagement() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-gold">Hubs</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage hub-router instances across regions
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover">
          <Plus className="h-4 w-4" />
          Add Hub
        </button>
      </div>

      {/* Hub cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {mockHubs.map((hub) => (
          <HubCard key={hub.id} hub={hub} />
        ))}
      </div>
    </div>
  );
}

function HubCard({ hub }: { hub: Hub }) {
  const capacityPercent =
    hub.capacity > 0
      ? Math.round((hub.connected_clients / hub.capacity) * 100)
      : 0;

  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-6 transition-colors hover:border-border-light">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              "rounded-lg p-2.5",
              hub.status === "healthy" && "bg-success/10",
              hub.status === "degraded" && "bg-warning/10",
              hub.status === "offline" && "bg-error/10",
            )}
          >
            <Server
              className={clsx(
                "h-6 w-6",
                hub.status === "healthy" && "text-success",
                hub.status === "degraded" && "text-warning",
                hub.status === "offline" && "text-error",
              )}
            />
          </div>
          <div>
            <h3 className="text-base font-semibold text-text-primary">
              {hub.name}
            </h3>
            <p className="text-xs text-text-muted">{hub.endpoint}</p>
          </div>
        </div>
        <span
          className={clsx(
            "rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
            hub.status === "healthy" && "bg-success/10 text-success",
            hub.status === "degraded" && "bg-warning/10 text-warning",
            hub.status === "offline" && "bg-error/10 text-error",
          )}
        >
          {hub.status}
        </span>
      </div>

      {/* Stats grid */}
      <div className="mt-5 grid grid-cols-3 gap-4">
        <div className="rounded-lg bg-bg-primary p-3">
          <div className="flex items-center gap-1.5 text-text-muted">
            <Users className="h-3.5 w-3.5" />
            <span className="text-xs">Clients</span>
          </div>
          <p className="mt-1 text-lg font-bold text-text-primary">
            {hub.connected_clients}
          </p>
        </div>
        <div className="rounded-lg bg-bg-primary p-3">
          <div className="flex items-center gap-1.5 text-text-muted">
            <Clock className="h-3.5 w-3.5" />
            <span className="text-xs">Uptime</span>
          </div>
          <p className="mt-1 text-lg font-bold text-text-primary">
            {formatUptime(hub.uptime_seconds)}
          </p>
        </div>
        <div className="rounded-lg bg-bg-primary p-3">
          <div className="flex items-center gap-1.5 text-text-muted">
            <Activity className="h-3.5 w-3.5" />
            <span className="text-xs">Version</span>
          </div>
          <p className="mt-1 text-lg font-bold text-text-primary">
            {hub.version}
          </p>
        </div>
      </div>

      {/* Capacity bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs">
          <span className="flex items-center gap-1 text-text-muted">
            <Gauge className="h-3.5 w-3.5" />
            Capacity
          </span>
          <span className="text-text-secondary">
            {hub.connected_clients}/{hub.capacity} ({capacityPercent}%)
          </span>
        </div>
        <div className="mt-1.5 h-2 rounded-full bg-bg-primary">
          <div
            className={clsx(
              "h-2 rounded-full transition-all",
              capacityPercent > 80
                ? "bg-warning"
                : capacityPercent > 0
                  ? "bg-success"
                  : "bg-bg-tertiary",
            )}
            style={{ width: `${capacityPercent}%` }}
          />
        </div>
      </div>
    </div>
  );
}
