import { ComponentType, lazy } from 'react';

export interface ChartProps {
  data: Array<{
    timestamp: string;
    latency?: number;
    throughput?: number;
    [key: string]: unknown;
  }>;
}

export function useLazyLoadChart(): ComponentType<ChartProps> | null {
  const LazyChart = lazy(() => import('../components/LiveChart'));
  return LazyChart as unknown as ComponentType<ChartProps>;
}
