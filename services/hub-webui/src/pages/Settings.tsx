import { useState } from "react";
import {
  Settings as SettingsIcon,
  Save,
  Globe,
  Shield,
  Bell,
  Database,
  ChevronDown,
} from "lucide-react";
import clsx from "clsx";

type SettingsTab = "general" | "security" | "notifications" | "advanced";

const tabs: { key: SettingsTab; label: string; icon: typeof Globe }[] = [
  { key: "general", label: "General", icon: Globe },
  { key: "security", label: "Security", icon: Shield },
  { key: "notifications", label: "Notifications", icon: Bell },
  { key: "advanced", label: "Advanced", icon: Database },
];

export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("general");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-gold">Settings</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Configure your Tobogganing hub deployment
        </p>
      </div>

      <div className="flex gap-6">
        {/* Tabs */}
        <nav className="w-48 shrink-0 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={clsx(
                "flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                activeTab === tab.key
                  ? "bg-accent/10 text-text-gold"
                  : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary",
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="flex-1 rounded-xl border border-border bg-bg-secondary p-6">
          {activeTab === "general" && <GeneralSettings />}
          {activeTab === "security" && <SecuritySettings />}
          {activeTab === "notifications" && <NotificationSettings />}
          {activeTab === "advanced" && <AdvancedSettings />}
        </div>
      </div>
    </div>
  );
}

function GeneralSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <SettingsIcon className="h-5 w-5 text-accent" />
        <h2 className="text-lg font-semibold text-text-gold">
          General Settings
        </h2>
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Deployment Name
          </label>
          <input
            type="text"
            defaultValue="Production Hub"
            className="w-full max-w-md rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Admin Contact Email
          </label>
          <input
            type="email"
            defaultValue="admin@corp.io"
            className="w-full max-w-md rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Default Hub Region
          </label>
          <div className="relative max-w-md">
            <select className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
              <option>US East (Virginia)</option>
              <option>US West (Oregon)</option>
              <option>EU West (Ireland)</option>
              <option>AP South (Mumbai)</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
          </div>
        </div>
      </div>

      <button className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover">
        <Save className="h-4 w-4" />
        Save Changes
      </button>
    </div>
  );
}

function SecuritySettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Shield className="h-5 w-5 text-accent" />
        <h2 className="text-lg font-semibold text-text-gold">
          Security Settings
        </h2>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between rounded-lg bg-bg-primary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">
              Enforce MFA for Admins
            </p>
            <p className="text-xs text-text-muted">
              Require multi-factor authentication for admin accounts
            </p>
          </div>
          <button className="text-accent">
            <span className="rounded-full bg-accent/10 px-3 py-1 text-xs font-medium">
              Enabled
            </span>
          </button>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-bg-primary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">
              Session Timeout
            </p>
            <p className="text-xs text-text-muted">
              Automatically log out inactive users
            </p>
          </div>
          <div className="relative">
            <select className="appearance-none rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none">
              <option>15 minutes</option>
              <option>30 minutes</option>
              <option>1 hour</option>
              <option>4 hours</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-2 h-3 w-3 text-text-muted" />
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-bg-primary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">
              API Rate Limiting
            </p>
            <p className="text-xs text-text-muted">
              Maximum API requests per minute per user
            </p>
          </div>
          <input
            type="number"
            defaultValue={100}
            className="w-24 rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-right text-sm text-text-primary focus:border-accent focus:outline-none"
          />
        </div>

        <div className="flex items-center justify-between rounded-lg bg-bg-primary p-4">
          <div>
            <p className="text-sm font-medium text-text-primary">
              TLS Minimum Version
            </p>
            <p className="text-xs text-text-muted">
              Minimum TLS version for client connections
            </p>
          </div>
          <div className="relative">
            <select className="appearance-none rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none">
              <option>TLS 1.3</option>
              <option>TLS 1.2</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-2 h-3 w-3 text-text-muted" />
          </div>
        </div>
      </div>

      <button className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover">
        <Save className="h-4 w-4" />
        Save Changes
      </button>
    </div>
  );
}

function NotificationSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Bell className="h-5 w-5 text-accent" />
        <h2 className="text-lg font-semibold text-text-gold">
          Notification Settings
        </h2>
      </div>

      <div className="space-y-4">
        {[
          {
            title: "Hub Offline Alerts",
            description: "Notify when a hub goes offline",
            enabled: true,
          },
          {
            title: "Capacity Warnings",
            description: "Alert when hub capacity exceeds 80%",
            enabled: true,
          },
          {
            title: "Policy Violations",
            description: "Notify on repeated policy violations",
            enabled: false,
          },
          {
            title: "User Login Events",
            description: "Alert on new user logins",
            enabled: false,
          },
        ].map((item) => (
          <div
            key={item.title}
            className="flex items-center justify-between rounded-lg bg-bg-primary p-4"
          >
            <div>
              <p className="text-sm font-medium text-text-primary">
                {item.title}
              </p>
              <p className="text-xs text-text-muted">{item.description}</p>
            </div>
            <span
              className={clsx(
                "rounded-full px-3 py-1 text-xs font-medium",
                item.enabled
                  ? "bg-accent/10 text-accent"
                  : "bg-bg-tertiary text-text-muted",
              )}
            >
              {item.enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
        ))}
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-text-secondary">
          Webhook URL (optional)
        </label>
        <input
          type="url"
          placeholder="https://hooks.slack.com/services/..."
          className="w-full max-w-md rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>

      <button className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover">
        <Save className="h-4 w-4" />
        Save Changes
      </button>
    </div>
  );
}

function AdvancedSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Database className="h-5 w-5 text-accent" />
        <h2 className="text-lg font-semibold text-text-gold">
          Advanced Settings
        </h2>
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Log Level
          </label>
          <div className="relative max-w-md">
            <select className="w-full appearance-none rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent">
              <option>info</option>
              <option>debug</option>
              <option>warn</option>
              <option>error</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-text-muted" />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Data Retention (days)
          </label>
          <input
            type="number"
            defaultValue={90}
            min={7}
            max={365}
            className="w-full max-w-md rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <p className="mt-1 text-xs text-text-muted">
            Audit logs and session data older than this will be purged
          </p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-text-secondary">
            Max Clients Per Hub
          </label>
          <input
            type="number"
            defaultValue={100}
            min={10}
            max={10000}
            className="w-full max-w-md rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>
      </div>

      <button className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg-primary hover:bg-accent-hover">
        <Save className="h-4 w-4" />
        Save Changes
      </button>
    </div>
  );
}
