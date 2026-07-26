import {
  Server,
  Monitor,
  Shield,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import clsx from "clsx";

// Mock data for dashboard display
const stats = {
  total_hubs: 4,
  healthy_hubs: 3,
  total_clients: 128,
  connected_clients: 112,
  total_policies: 24,
  active_policies: 18,
  active_sessions: 97,
};

const recentActivity = [
  {
    id: "1",
    type: "policy_decision",
    message: "Policy 'Block Malicious Domains' denied traffic from client-047",
    time: "2 min ago",
    status: "warning",
  },
  {
    id: "2",
    type: "auth",
    message: "User admin@corp.io logged in successfully",
    time: "5 min ago",
    status: "success",
  },
  {
    id: "3",
    type: "system",
    message: "Hub us-east-1 health check passed",
    time: "8 min ago",
    status: "success",
  },
  {
    id: "4",
    type: "admin_action",
    message: "Policy 'Allow Internal DNS' updated by admin",
    time: "15 min ago",
    status: "info",
  },
  {
    id: "5",
    type: "system",
    message: "Hub eu-west-1 capacity at 82%",
    time: "22 min ago",
    status: "warning",
  },
];

const hubOverview = [
  { name: "us-east-1", status: "healthy", clients: 45, capacity: 68 },
  { name: "us-west-2", status: "healthy", clients: 38, capacity: 55 },
  { name: "eu-west-1", status: "degraded", clients: 29, capacity: 82 },
  { name: "ap-south-1", status: "healthy", clients: 0, capacity: 0 },
];

interface StatCardProps {
  title: string;
  value: number;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: "up" | "down";
  trendValue?: string;
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  trendValue,
}: StatCardProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-text-secondary">{title}</p>
          <p className="mt-1 text-3xl font-bold text-text-gold">{value}</p>
          <p className="mt-1 text-xs text-text-muted">{subtitle}</p>
        </div>
        <div className="rounded-lg bg-accent/10 p-2.5">
          <Icon className="h-5 w-5 text-accent" />
        </div>
      </div>
      {trend && trendValue && (
        <div className="mt-3 flex items-center gap-1 text-xs">
          {trend === "up" ? (
            <ArrowUpRight className="h-3 w-3 text-success" />
          ) : (
            <ArrowDownRight className="h-3 w-3 text-error" />
          )}
          <span
            className={trend === "up" ? "text-success" : "text-error"}
          >
            {trendValue}
          </span>
          <span className="text-text-muted">vs last hour</span>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-gold">Dashboard</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Overview of your Tobogganing hub network
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Hubs"
          value={stats.total_hubs}
          subtitle={`${stats.healthy_hubs} healthy`}
          icon={Server}
          trend="up"
          trendValue="100%"
        />
        <StatCard
          title="Connected Clients"
          value={stats.connected_clients}
          subtitle={`of ${stats.total_clients} total`}
          icon={Monitor}
          trend="up"
          trendValue="+3"
        />
        <StatCard
          title="Active Policies"
          value={stats.active_policies}
          subtitle={`of ${stats.total_policies} total`}
          icon={Shield}
        />
        <StatCard
          title="Active Sessions"
          value={stats.active_sessions}
          subtitle="Current connections"
          icon={Activity}
          trend="up"
          trendValue="+12"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Hub overview */}
        <div className="rounded-xl border border-border bg-bg-secondary p-6">
          <h2 className="mb-4 text-lg font-semibold text-text-gold">
            Hub Status
          </h2>
          <div className="space-y-3">
            {hubOverview.map((hub) => (
              <div
                key={hub.name}
                className="flex items-center justify-between rounded-lg bg-bg-primary p-4"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={clsx(
                      "h-2.5 w-2.5 rounded-full",
                      hub.status === "healthy" && "bg-success",
                      hub.status === "degraded" && "bg-warning",
                      hub.status === "offline" && "bg-error",
                    )}
                  />
                  <div>
                    <p className="text-sm font-medium text-text-primary">
                      {hub.name}
                    </p>
                    <p className="text-xs text-text-muted">
                      {hub.clients} clients
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-text-primary">
                    {hub.capacity}%
                  </p>
                  <div className="mt-1 h-1.5 w-20 rounded-full bg-bg-tertiary">
                    <div
                      className={clsx(
                        "h-1.5 rounded-full",
                        hub.capacity > 80
                          ? "bg-warning"
                          : hub.capacity > 0
                            ? "bg-success"
                            : "bg-bg-tertiary",
                      )}
                      style={{ width: `${hub.capacity}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent activity */}
        <div className="rounded-xl border border-border bg-bg-secondary p-6">
          <h2 className="mb-4 text-lg font-semibold text-text-gold">
            Recent Activity
          </h2>
          <div className="space-y-3">
            {recentActivity.map((event) => (
              <div
                key={event.id}
                className="flex items-start gap-3 rounded-lg bg-bg-primary p-3"
              >
                {event.status === "success" ? (
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                ) : event.status === "warning" ? (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                ) : (
                  <Activity className="mt-0.5 h-4 w-4 shrink-0 text-info" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-text-primary">{event.message}</p>
                  <p className="mt-0.5 text-xs text-text-muted">{event.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
