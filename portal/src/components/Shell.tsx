import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function Shell() {
  return (
    <div className="flex min-h-screen bg-slate-900">
      <Sidebar />
      <main className="flex-1 lg:ml-64 lg:pt-0 pt-16 pb-8">
        <Outlet />
      </main>
    </div>
  );
}
