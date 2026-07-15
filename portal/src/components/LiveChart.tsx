import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export interface LiveChartProps {
  data: Array<Record<string, unknown> & {
    timestamp: string;
    latency?: number;
    throughput?: number;
  }>;
}

export default function LiveChart({ data }: LiveChartProps) {
  console.log('[LiveChart] Render { points:', data.length, '}');

  if (data.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-slate-400">
        No data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
        <XAxis stroke="#94a3b8" dataKey="timestamp" />
        <YAxis stroke="#94a3b8" />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1e293b',
            border: '1px solid #475569',
            borderRadius: '4px',
            color: '#fbbf24',
          }}
        />
        <Legend />
        {data.some((d) => d.latency !== undefined) && (
          <Line
            type="monotone"
            dataKey="latency"
            stroke="#0ea5e9"
            dot={{ fill: '#fbbf24', r: 3 }}
            activeDot={{ r: 5 }}
            name="Latency (ms)"
          />
        )}
        {data.some((d) => d.throughput !== undefined) && (
          <Line
            type="monotone"
            dataKey="throughput"
            stroke="#10b981"
            dot={{ fill: '#fbbf24', r: 3 }}
            activeDot={{ r: 5 }}
            name="Throughput (Mbps)"
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
