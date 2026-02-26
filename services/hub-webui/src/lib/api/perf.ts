import apiClient from '../api';

export interface PerfMetric {
  id: number;
  source_id: string;
  source_type: string;
  target_id: string;
  protocol: string;
  latency_ms: number;
  jitter_ms: number | null;
  packet_loss_pct: number | null;
  throughput_mbps: number | null;
  timestamp: string;
}

export interface PerfSummaryPair {
  source_id: string;
  target_id: string;
  protocols: Record<
    string,
    {
      latest_latency_ms: number;
      latest_jitter_ms: number | null;
      latest_packet_loss_pct: number | null;
      latest_throughput_mbps: number | null;
      last_measured: string;
    }
  >;
}

export async function fetchPerfMetrics(params?: {
  cluster_id?: string;
  protocol?: string;
  limit?: number;
}) {
  const { data } = await apiClient.get<{
    status: string;
    data: { metrics: PerfMetric[] };
    meta: { count: number; limit: number };
  }>('/perf/metrics', { params });
  return data;
}

export async function fetchPerfSummary() {
  const { data } = await apiClient.get<{
    status: string;
    data: { pairs: PerfSummaryPair[] };
    meta: { pair_count: number };
  }>('/perf/summary');
  return data;
}
