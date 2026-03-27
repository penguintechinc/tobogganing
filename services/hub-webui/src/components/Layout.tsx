import { useState } from "react";
import { LogOut, User as UserIcon } from "lucide-react";
import clsx from "clsx";
import { useAuth } from "../lib/auth";
import Sidebar from "./Sidebar";
import type { ReactNode } from "react";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div className="min-h-screen bg-bg-primary">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      {/* Main content area */}
      <div
        className={clsx(
          "flex min-h-screen flex-col transition-all duration-300",
          sidebarCollapsed ? "ml-16" : "ml-60",
        )}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-end border-b border-border bg-bg-secondary/95 px-6 backdrop-blur">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <UserIcon className="h-4 w-4 text-text-secondary" />
              <span className="text-text-primary">{user?.name}</span>
              <span className="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium capitalize text-text-gold">
                {user?.role}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
