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
} from "lucide-react";
import { SidebarMenu, type MenuCategory } from "@penguintechinc/react-libs";
import { useNavigate, useLocation } from "react-router-dom";

interface SidebarProps {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

const categories: MenuCategory[] = [
  {
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Policies", href: "/policies", icon: Shield },
      { name: "Clients", href: "/clients", icon: Monitor },
      { name: "Hubs", href: "/hubs", icon: Server },
    ],
  },
  {
    header: "Management",
    items: [
      { name: "Users", href: "/users", icon: Users },
      { name: "Identity", href: "/identity", icon: Fingerprint },
      { name: "Settings", href: "/settings", icon: Settings },
    ],
  },
  {
    header: "Observability",
    items: [
      { name: "Audit Logs", href: "/audit", icon: ScrollText },
    ],
  },
];

export default function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <SidebarMenu
      logo={
        <div className="flex items-center gap-3">
          <Snowflake className="h-7 w-7 text-amber-400" />
          <span className="text-lg font-bold text-amber-400">Tobogganing</span>
        </div>
      }
      categories={categories}
      currentPath={pathname}
      onNavigate={navigate}
      mobileOpen={mobileOpen}
      onMobileClose={onMobileClose}
      closeOnNavigate
    />
  );
}
