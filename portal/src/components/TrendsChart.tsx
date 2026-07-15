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

export interface TrendDataPoint {
  timestamp: string;
  value: number;
}

export interface TrendsChartProps {
  data: TrendDataPoint[];
}

export default function TrendsChart({ data }: TrendsChartProps) {
  if (data.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        No trend data available
      </div>
    );
  }

  const chartData = data.map((point) => ({
    name: new Date(point.timestamp).toLocaleDateString(),
    value: point.value,
  }));

  console.log('[TrendsChart] Render { points:', chartData.length, '}');

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
          <XAxis stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #475569',
              borderRadius: '4px',
              color: '#fbbf24',
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#0ea5e9"
            dot={{ fill: '#fbbf24', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
