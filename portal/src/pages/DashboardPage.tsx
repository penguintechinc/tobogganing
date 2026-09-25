import React from 'react';
import { useAuth } from '../context/AuthContext';
import { useManifest } from '../hooks/useManifest';

export function DashboardPage() {
  const { user } = useAuth();
  const { data: manifest, isLoading } = useManifest();

  return (
    <div className="p-8">
      <h1 className="text-4xl font-bold text-amber-400 mb-2">Welcome</h1>
      <p className="text-amber-600 mb-8">
        {user?.email} • Role: {user?.role}
      </p>

      {isLoading && <div className="text-amber-400">Loading modules...</div>}

      {manifest && (
        <>
          <h2 className="text-2xl font-bold text-amber-400 mb-4">Modules</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {manifest.modules.map((module) => (
              <div
                key={module.name}
                className="bg-slate-800 rounded-lg border border-slate-700 p-6 hover:border-sky-500 transition-colors"
              >
                <h3 className="text-lg font-semibold text-amber-400 mb-2">{module.name}</h3>
                <p className="text-sm text-amber-600 mb-4">{module.nav.length} views</p>
                <div className="flex flex-wrap gap-2">
                  {module.nav.slice(0, 3).map((nav) => (
                    <span
                      key={nav.path}
                      className="inline-block px-2 py-1 text-xs bg-slate-700 text-amber-300 rounded"
                    >
                      {nav.label}
                    </span>
                  ))}
                  {module.nav.length > 3 && (
                    <span className="inline-block px-2 py-1 text-xs text-amber-600">
                      +{module.nav.length - 3} more
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
