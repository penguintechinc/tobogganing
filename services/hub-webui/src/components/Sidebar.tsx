import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Shield,
  Monitor,
  Server,
  Users,
  Fingerprint,
  Settings,
  ScrollText,
  Snowflake,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import clsx from "clsx";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/policies", icon: Shield, label: "Policies" },
  { to: "/clients", icon: Monitor, label: "Clients" },
  { to: "/hubs", icon: Server, label: "Hubs" },
  { to: "/users", icon: Users, label: "Users" },
  { to: "/identity", icon: Fingerprint, label: "Identity" },
  { to: "/settings", icon: Settings, label: "Settings" },
  { to: "/audit", icon: ScrollText, label: "Audit Logs" },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={clsx(
        "fixed left-0 top-0 z-40 flex h-full flex-col border-r border-border bg-bg-secondary transition-all duration-300",
        collapsed ? "w-16" : "w-60",
      )}
    >
      {/* Logo / Title */}
      <div className="flex h-16 items-center border-b border-border px-4">
        <Snowflake className="h-7 w-7 shrink-0 text-accent" />
        {!collapsed && (
          <span className="ml-3 text-lg font-bold text-text-gold">
            Tobogganing
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-accent/10 text-text-gold"
                      : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary",
                    collapsed && "justify-center",
                  )
                }
                title={collapsed ? item.label : undefined}
              >
                <item.icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span className="ml-3">{item.label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-border p-2">
        <button
          onClick={onToggle}
          className="flex w-full items-center justify-center rounded-lg p-2 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <ChevronLeft className="h-5 w-5" />
          )}
        </button>
      </div>
    </aside>
  );
}
