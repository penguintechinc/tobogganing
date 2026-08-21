import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { SpeedTestChartPoint } from '../hooks/useSpeedTest';

export interface SpeedTestChartProps {
  data: SpeedTestChartPoint[];
}

/** Realtime Mbps line chart driven by per-tick download/upload progress samples. */
export default function SpeedTestChart({ data }: SpeedTestChartProps) {
  if (data.length === 0) {
    return <div className="text-center py-8 text-slate-400">No samples yet</div>;
  }

  const chartData = data.map((point, idx) => ({
    name: String(idx),
    mbps: Number(point.mbps.toFixed(2)),
    phase: point.label,
  }));

  console.log('[SpeedTestChart] Render { points:', chartData.length, '}');

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
          <XAxis dataKey="name" stroke="#94a3b8" />
          <YAxis
            stroke="#94a3b8"
            label={{ value: 'Mbps', angle: -90, position: 'insideLeft', fill: '#94a3b8' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#fbbf24',
            }}
            labelFormatter={(_label, payload) => {
              const phase = payload?.[0]?.payload?.phase as string | undefined;
              return phase ? `Phase: ${phase}` : '';
            }}
          />
          <Line type="monotone" dataKey="mbps" stroke="#0ea5e9" dot={false} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
