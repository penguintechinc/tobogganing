import React from 'react';

interface PlaceholderViewProps {
  module: string;
  view: string;
}

export function PlaceholderView({ module, view }: PlaceholderViewProps) {
  return (
    <div className="p-8">
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
        <h1 className="text-2xl font-bold text-amber-400 mb-2">
          {view.charAt(0).toUpperCase() + view.slice(1)}
        </h1>
        <p className="text-amber-600 mb-4">Module: {module}</p>
        <p className="text-amber-700">View implementation coming soon</p>
      </div>
    </div>
  );
}
