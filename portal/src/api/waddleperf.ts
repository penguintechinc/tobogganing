import apiClient from './client';

export interface Device {
  id: string;
  name: string;
  serial: string;
  hostname: string;
  os: string;
  org_unit_id: string;
  status: string;
  last_heartbeat: string | null;
  created_at: string;
}

export interface DevicesResponse {
  devices: Device[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface Test {
  id: string;
  device_id: string;
  test_type: string;
  status: string;
  target: string | null;
  latency_ms: number | null;
  throughput: number | null;
  created_at: string;
}

export interface TestsResponse {
  tests: Test[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface StatsSummary {
  total_tests: number;
  total_devices: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_throughput: number;
}

export interface StatsSummaryResponse {
  summary: StatsSummary;
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface TrendDataPoint {
  timestamp: string;
  value: number;
}

export interface StatsTrendsResponse {
  trends: TrendDataPoint[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export async function listDevices(): Promise<Device[]> {
  console.log('[waddleperf] listDevices');
  const response = await apiClient.get<DevicesResponse>(
    '/waddleperf_cluster/devices'
  );
  return response.data.devices;
}

export async function listTests(): Promise<Test[]> {
  console.log('[waddleperf] listTests');
  const response = await apiClient.get<TestsResponse>('/waddleperf_cluster/tests');
  return response.data.tests;
}

export async function getStatsSummary(): Promise<StatsSummary> {
  console.log('[waddleperf] getStatsSummary');
  const response = await apiClient.get<StatsSummaryResponse>(
    '/waddleperf_cluster/stats/summary'
  );
  return response.data.summary;
}

export async function getStatsTrends(): Promise<TrendDataPoint[]> {
  console.log('[waddleperf] getStatsTrends');
  const response = await apiClient.get<StatsTrendsResponse>(
    '/waddleperf_cluster/stats/trends'
  );
  return response.data.trends;
}
