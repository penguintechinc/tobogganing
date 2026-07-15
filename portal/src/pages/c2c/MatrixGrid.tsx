import React from 'react';
import { MatrixCell } from '../../api/c2c';

interface MatrixGridProps {
  regions: string[];
  cells: MatrixCell[];
  testType: string;
}

function getCellColor(cell: MatrixCell): string {
  const lossPercent = cell.loss_pct;

  if (lossPercent < 1) {
    return 'bg-green-900 text-green-100';
  } else if (lossPercent < 5) {
    return 'bg-amber-900 text-amber-100';
  } else {
    return 'bg-red-900 text-red-100';
  }
}

function formatMetric(latency: number): string {
  return `${latency.toFixed(2)}ms`;
}

export function MatrixGrid({
  regions,
  cells,
  testType,
}: MatrixGridProps) {
  const sortedRegions = [...regions].sort();
  const cellMap = new Map<string, MatrixCell>();

  for (const cell of cells) {
    const key = `${cell.source}|${cell.destination}`;
    cellMap.set(key, cell);
  }

  console.log('[MatrixGrid] Render { regions:', sortedRegions.length, ', cells:', cells.length, ', testType:', testType, '}');

  return (
    <div className="overflow-x-auto">
      <div
        className="inline-grid gap-px bg-slate-700 p-2 rounded"
        style={{
          gridTemplateColumns: `auto repeat(${sortedRegions.length}, 1fr)`,
        }}
      >
        <div className="bg-slate-800 p-2 min-w-[120px]">
          <span className="text-xs font-semibold text-amber-300">
            {testType}
          </span>
        </div>

        {sortedRegions.map((region) => (
          <div
            key={`header-${region}`}
            className="bg-slate-800 p-2 min-w-[100px] text-center"
          >
            <span className="text-xs font-semibold text-amber-300">
              {region}
            </span>
          </div>
        ))}

        {sortedRegions.map((source) => (
          <React.Fragment key={`row-${source}`}>
            <div className="bg-slate-800 p-2 min-w-[120px]">
              <span className="text-xs font-semibold text-amber-300">
                {source}
              </span>
            </div>

            {sortedRegions.map((dest) => {
              const cellKey = `${source}|${dest}`;
              const cell = cellMap.get(cellKey);

              if (!cell) {
                return (
                  <div
                    key={`cell-${cellKey}`}
                    className="bg-slate-700 p-2 min-w-[100px] text-center"
                  >
                    <span className="text-xs text-slate-400">—</span>
                  </div>
                );
              }

              return (
                <div
                  key={`cell-${cellKey}`}
                  className={`${getCellColor(cell)} p-2 min-w-[100px] text-center rounded`}
                >
                  <div className="text-xs font-semibold">
                    {formatMetric(cell.latency)}
                  </div>
                  <div className="text-xs opacity-80">
                    {cell.loss_pct.toFixed(1)}% loss
                  </div>
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
