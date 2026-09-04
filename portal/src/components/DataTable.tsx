import React, { useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';

export interface ColumnConfig<T> {
  key: keyof T;
  label: string;
  sortable?: boolean;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

export interface DataTableProps<T extends { id?: string }> {
  columns: ColumnConfig<T>[];
  data: T[];
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  pageSize?: number;
}

export function DataTable<T extends { id?: string }>({
  columns,
  data,
  isLoading = false,
  error = null,
  onRetry,
  pageSize = 25,
}: DataTableProps<T>) {
  const [sortColumn, setSortColumn] = useState<keyof T | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);

  const handleSort = (column: keyof T) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
    setCurrentPage(1);
  };

  const displayData = [...data];

  if (sortColumn) {
    displayData.sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];

      if (aVal == null || bVal == null) {
        return 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
      }

      return 0;
    });
  }

  const startIdx = (currentPage - 1) * pageSize;
  const paginatedData = displayData.slice(startIdx, startIdx + pageSize);
  const totalPages = Math.ceil(displayData.length / pageSize);

  console.log('[DataTable] Render { rows:', paginatedData.length, 'page:', currentPage, '}');

  if (isLoading) {
    return (
      <div data-testid="datatable" className="w-full">
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-700 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="datatable" className="w-full">
        <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded">
          <p className="font-semibold">Error loading data</p>
          <p className="text-sm">{error.message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 px-3 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-sm"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  if (paginatedData.length === 0) {
    return (
      <div data-testid="datatable" className="w-full">
        <div className="text-center py-8 text-amber-300">
          <p>No data available</p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="datatable" className="w-full">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-slate-800 border-b border-slate-700">
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className="px-4 py-3 text-left text-amber-400 font-semibold"
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                  style={{
                    cursor: col.sortable !== false ? 'pointer' : 'default',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span>{col.label}</span>
                    {col.sortable !== false && sortColumn === col.key && (
                      <>
                        {sortDirection === 'asc' ? (
                          <ChevronUp size={16} />
                        ) : (
                          <ChevronDown size={16} />
                        )}
                      </>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row, idx) => (
              <tr
                key={row.id || idx}
                data-testid="datatable-row"
                className="border-b border-slate-700 hover:bg-slate-700 transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={`${row.id || idx}-${String(col.key)}`}
                    className="px-4 py-3 text-slate-200"
                  >
                    {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '-')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 px-4 py-3 bg-slate-800 rounded">
          <span className="text-slate-300 text-sm">
            Page {currentPage} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 bg-slate-700 hover:bg-sky-500 disabled:opacity-50 text-white rounded text-sm"
            >
              Prev
            </button>
            <button
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 bg-slate-700 hover:bg-sky-500 disabled:opacity-50 text-white rounded text-sm"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
