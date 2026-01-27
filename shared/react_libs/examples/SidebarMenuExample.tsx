import React, { useState } from 'react';
import { SidebarMenu, MenuCategory, MenuItem, SidebarColorConfig } from '../src/components';

// Example icons (you would import these from lucide-react in a real app)
const DashboardIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const UsersIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
  </svg>
);

const SettingsIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

const LogoutIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
);

/**
 * Example: Default Elder-Inspired Sidebar
 * Uses the default Elder color scheme (slate dark with blue accent)
 */
export const DefaultElderSidebarExample: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Dashboard', href: '/', icon: DashboardIcon },
      ],
    },
    {
      header: 'Management',
      collapsible: true,
      items: [
        { name: 'Users', href: '/users', icon: UsersIcon },
        { name: 'Teams', href: '/teams', icon: UsersIcon },
        { name: 'Organizations', href: '/organizations', icon: UsersIcon },
      ],
    },
    {
      header: 'Administration',
      collapsible: true,
      items: [
        { name: 'Settings', href: '/admin/settings', icon: SettingsIcon, roles: ['admin'] },
        { name: 'Audit Logs', href: '/admin/audit', icon: SettingsIcon, roles: ['admin'] },
      ],
    },
  ];

  const footerItems: MenuItem[] = [
    { name: 'Profile', href: '/profile', icon: UsersIcon },
    { name: 'Logout', href: '/logout', icon: LogoutIcon },
  ];

  return (
    <div className="h-screen bg-slate-900">
      <SidebarMenu
        logo={<img src="/logo.png" alt="Logo" className="h-12 w-auto" />}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={footerItems}
        userRole="admin"
        // No colors prop = Elder default (slate-800 bg, blue accent)
      />

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">
          <h1 className="text-2xl font-bold text-white mb-4">Current Page: {currentPath}</h1>
          <p className="text-slate-300">Click sidebar items to navigate</p>
        </main>
      </div>
    </div>
  );
};

/**
 * Example: Custom Navy & Gold Theme
 * Matches the FormModalBuilder default theme
 */
export const NavyGoldSidebarExample: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/dashboard');

  const navyGoldTheme: SidebarColorConfig = {
    sidebarBackground: 'bg-slate-900',
    sidebarBorder: 'border-slate-700',
    logoSectionBorder: 'border-slate-700',
    categoryHeaderText: 'text-amber-400',
    menuItemText: 'text-amber-300',
    menuItemHover: 'hover:bg-slate-800 hover:text-amber-200',
    menuItemActive: 'bg-amber-500',
    menuItemActiveText: 'text-slate-900',
    collapseIndicator: 'text-amber-400',
    footerBorder: 'border-slate-700',
    footerButtonText: 'text-amber-300',
    footerButtonHover: 'hover:bg-slate-800 hover:text-amber-200',
    scrollbarTrack: 'bg-slate-900',
    scrollbarThumb: 'bg-slate-700',
    scrollbarThumbHover: 'hover:bg-slate-600',
  };

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Dashboard', href: '/dashboard', icon: DashboardIcon },
      ],
    },
    {
      header: 'Content',
      collapsible: true,
      items: [
        { name: 'Posts', href: '/posts', icon: DashboardIcon },
        { name: 'Pages', href: '/pages', icon: DashboardIcon },
        { name: 'Media', href: '/media', icon: DashboardIcon },
      ],
    },
  ];

  const footerItems: MenuItem[] = [
    { name: 'Account', href: '/account', icon: UsersIcon },
    { name: 'Sign Out', href: '/logout', icon: LogoutIcon },
  ];

  return (
    <div className="h-screen bg-slate-950">
      <SidebarMenu
        logo={<span className="text-2xl font-bold text-amber-400">GOLD</span>}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={footerItems}
        colors={navyGoldTheme}
      />

      <div className="pl-64">
        <main className="p-8">
          <h1 className="text-2xl font-bold text-amber-400 mb-4">Navy & Gold Theme</h1>
          <p className="text-slate-300">Current: {currentPath}</p>
        </main>
      </div>
    </div>
  );
};

/**
 * Example: Emerald Green Theme
 * Professional green theme for business apps
 */
export const EmeraldSidebarExample: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');

  const emeraldTheme: SidebarColorConfig = {
    sidebarBackground: 'bg-emerald-950',
    sidebarBorder: 'border-emerald-800',
    logoSectionBorder: 'border-emerald-800',
    categoryHeaderText: 'text-emerald-400',
    menuItemText: 'text-emerald-200',
    menuItemHover: 'hover:bg-emerald-900 hover:text-emerald-100',
    menuItemActive: 'bg-emerald-600',
    menuItemActiveText: 'text-white',
    collapseIndicator: 'text-emerald-400',
    footerBorder: 'border-emerald-800',
    footerButtonText: 'text-emerald-200',
    footerButtonHover: 'hover:bg-emerald-900 hover:text-emerald-100',
    scrollbarTrack: 'bg-emerald-950',
    scrollbarThumb: 'bg-emerald-800',
    scrollbarThumbHover: 'hover:bg-emerald-700',
  };

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Overview', href: '/', icon: DashboardIcon },
      ],
    },
    {
      header: 'Financial',
      collapsible: true,
      items: [
        { name: 'Accounts', href: '/accounts', icon: DashboardIcon },
        { name: 'Transactions', href: '/transactions', icon: DashboardIcon },
        { name: 'Reports', href: '/reports', icon: DashboardIcon },
      ],
    },
  ];

  return (
    <div className="h-screen bg-emerald-900">
      <SidebarMenu
        logo={<span className="text-xl font-bold text-emerald-400">FinTech</span>}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={[
          { name: 'Settings', href: '/settings', icon: SettingsIcon },
          { name: 'Logout', href: '/logout', icon: LogoutIcon },
        ]}
        colors={emeraldTheme}
      />

      <div className="pl-64">
        <main className="p-8">
          <h1 className="text-2xl font-bold text-emerald-400">Emerald Theme</h1>
        </main>
      </div>
    </div>
  );
};

/**
 * Example: Light Mode Sidebar
 * Traditional light theme
 */
export const LightSidebarExample: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');

  const lightTheme: SidebarColorConfig = {
    sidebarBackground: 'bg-white',
    sidebarBorder: 'border-gray-200',
    logoSectionBorder: 'border-gray-200',
    categoryHeaderText: 'text-gray-600',
    menuItemText: 'text-gray-700',
    menuItemHover: 'hover:bg-gray-100 hover:text-gray-900',
    menuItemActive: 'bg-blue-600',
    menuItemActiveText: 'text-white',
    collapseIndicator: 'text-gray-500',
    footerBorder: 'border-gray-200',
    footerButtonText: 'text-gray-700',
    footerButtonHover: 'hover:bg-gray-100 hover:text-gray-900',
    scrollbarTrack: 'bg-white',
    scrollbarThumb: 'bg-gray-300',
    scrollbarThumbHover: 'hover:bg-gray-400',
  };

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Home', href: '/', icon: DashboardIcon },
      ],
    },
    {
      header: 'Main',
      collapsible: true,
      items: [
        { name: 'Projects', href: '/projects', icon: DashboardIcon },
        { name: 'Tasks', href: '/tasks', icon: DashboardIcon },
      ],
    },
  ];

  return (
    <div className="h-screen bg-gray-50">
      <SidebarMenu
        logo={<span className="text-xl font-bold text-gray-900">Light</span>}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={[{ name: 'Logout', href: '/logout', icon: LogoutIcon }]}
        colors={lightTheme}
      />

      <div className="pl-64">
        <main className="p-8">
          <h1 className="text-2xl font-bold text-gray-900">Light Mode Sidebar</h1>
        </main>
      </div>
    </div>
  );
};
