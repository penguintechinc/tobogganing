import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, LogOut } from 'lucide-react';
import { useManifest } from '../hooks/useManifest';
import { useAuth } from '../context/AuthContext';
import { getIconComponent } from '../utils/icons';

export function Sidebar() {
  const { data: manifest } = useManifest();
  const { logout, user } = useAuth();
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
  };

  if (!manifest) {
    return null;
  }

  const sidebarContent = (
    <>
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-2xl font-bold text-amber-400">Tobogganing</h1>
        <p className="text-sm text-amber-600">Portal</p>
      </div>

      <nav className="flex-1 overflow-y-auto p-4 space-y-2">
        {manifest.modules.map((module) => (
          <div key={module.name}>
            <p className="px-4 py-2 text-xs font-semibold text-amber-500 uppercase tracking-wider">
              {module.name}
            </p>
            <div className="space-y-1">
              {module.nav.map((navEntry) => {
                const slug = navEntry.label.toLowerCase().replace(/\s+/g, '-');
                const path = `/m/${module.name}/${slug}`;
                const isActive = location.pathname === path;
                const IconComponent = getIconComponent(navEntry.icon);

                return (
                  <Link
                    key={path}
                    to={path}
                    onClick={() => setIsOpen(false)}
                    className={`flex items-center gap-3 px-4 py-2 rounded-lg transition-colors text-sm font-medium ${
                      isActive
                        ? 'bg-sky-600 text-white'
                        : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'
                    }`}
                  >
                    {IconComponent && <IconComponent className="w-5 h-5" />}
                    <span>{navEntry.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-slate-700 p-4 space-y-2">
        {user && (
          <div className="px-4 py-2 text-xs text-amber-600 truncate" title={user.email}>
            {user.email.split('@')[0]}@...
          </div>
        )}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-4 py-2 rounded-lg text-amber-400 hover:bg-slate-700 hover:text-amber-200 transition-colors text-sm font-medium"
        >
          <LogOut className="w-5 h-5" />
          <span>Logout</span>
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden lg:flex fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700 flex-col">
        {sidebarContent}
      </div>

      {/* Mobile header with hamburger */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-4 z-50">
        <h1 className="text-xl font-bold text-amber-400">Tobogganing</h1>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="text-amber-400 hover:text-amber-200"
          aria-label="Toggle menu"
        >
          {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile sidebar overlay */}
      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black bg-opacity-50 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      {isOpen && (
        <div className="lg:hidden fixed top-16 left-0 right-0 bottom-0 bg-slate-800 border-r border-slate-700 overflow-y-auto z-40 flex flex-col">
          {sidebarContent}
        </div>
      )}
    </>
  );
}
