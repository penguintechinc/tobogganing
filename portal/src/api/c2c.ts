import apiClient from './client';

export interface Endpoint {
  id: string;
  region: string;
  name: string;
  engine_url: string;
  target: string;
  enabled: boolean;
  visibility?: string;
  provider?: string;
  api_key?: string;
  created_at?: string;
}

export interface EndpointsResponse {
  endpoints: Endpoint[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface CreateEndpointPayload {
  region: string;
  name: string;
  engine_url: string;
  target: string;
  api_key?: string;
}

export interface Run {
  id: string;
  status: string;
  total_pairs: number;
  created_at: string;
  created_by?: string;
}

export interface RunsResponse {
  runs: Run[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface CreateRunPayload {
  test_types: string[];
  endpoint_ids?: string[];
}

export interface MatrixCell {
  source: string;
  destination: string;
  loss_pct: number;
  latency: number;
  test_type: string;
}

export interface MatrixData {
  regions: string[];
  cells: MatrixCell[];
}

export interface MatrixResponse {
  regions: string[];
  cells: MatrixCell[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface TrendPoint {
  timestamp: string;
  value: number;
}

export interface TrendsResponse {
  source: string;
  dest: string;
  test_type: string;
  trends: TrendPoint[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface RecurringJob {
  id: string;
  job_type: 'matrix_run' | 'node_health';
  interval_seconds: number;
  enabled: boolean;
  next_run_at?: string;
  created_at?: string;
}

export interface RecurringJobsResponse {
  jobs: RecurringJob[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface CreateRecurringPayload {
  endpoint_ids?: string[] | null;
  interval_seconds: number;
  job_type?: 'matrix_run' | 'node_health';
}

export interface Region {
  region: string;
  node_count: number;
  healthy_count: number;
  providers?: string[];
}

export interface RegionsResponse {
  regions: Region[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface VisibleNode extends Endpoint {
  is_public?: boolean;
  owner_tenant?: string;
}

export interface NodesResponse {
  nodes: VisibleNode[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export async function listEndpoints(): Promise<Endpoint[]> {
  console.log('[c2c] listEndpoints');
  const response = await apiClient.get<EndpointsResponse>('/perftest_c2c/endpoints');
  return response.data.endpoints;
}

export async function getEndpoint(id: string): Promise<Endpoint> {
  console.log('[c2c] getEndpoint { id:', id, '}');
  const response = await apiClient.get(`/perftest_c2c/endpoints/${id}`);
  return response.data as Endpoint;
}

export async function createEndpoint(payload: CreateEndpointPayload): Promise<Endpoint> {
  console.log('[c2c] createEndpoint { region:', payload.region, ', name:', payload.name, '}');
  const response = await apiClient.post('/perftest_c2c/endpoints', payload);
  return response.data as Endpoint;
}

export async function updateEndpoint(
  id: string,
  payload: Partial<CreateEndpointPayload>
): Promise<Endpoint> {
  console.log('[c2c] updateEndpoint { id:', id, '}');
  const response = await apiClient.patch(`/perftest_c2c/endpoints/${id}`, payload);
  return response.data as Endpoint;
}

export async function deleteEndpoint(id: string): Promise<void> {
  console.log('[c2c] deleteEndpoint { id:', id, '}');
  await apiClient.delete(`/perftest_c2c/endpoints/${id}`);
}

export async function listRuns(): Promise<Run[]> {
  console.log('[c2c] listRuns');
  const response = await apiClient.get<RunsResponse>('/perftest_c2c/runs');
  return response.data.runs;
}

export async function getRun(id: string): Promise<Run> {
  console.log('[c2c] getRun { id:', id, '}');
  const response = await apiClient.get(`/perftest_c2c/runs/${id}`);
  return response.data as Run;
}

export async function createRun(
  payload: CreateRunPayload
): Promise<{ run_id: string; total_pairs: number }> {
  console.log('[c2c] createRun { testTypes:', payload.test_types.length, '}');
  const response = await apiClient.post<{ run_id: string; total_pairs: number }>(
    '/perftest_c2c/runs',
    payload
  );
  return {
    run_id: response.data.run_id,
    total_pairs: response.data.total_pairs,
  };
}

export async function getLatestMatrix(testType: string): Promise<MatrixData> {
  console.log('[c2c] getLatestMatrix { testType:', testType, '}');
  const response = await apiClient.get<MatrixResponse>('/perftest_c2c/matrix/latest', {
    params: { test_type: testType },
  });
  return {
    regions: response.data.regions,
    cells: response.data.cells,
  };
}

export async function getRunMatrix(runId: string): Promise<MatrixData> {
  console.log('[c2c] getRunMatrix { runId:', runId, '}');
  const response = await apiClient.get<MatrixResponse>(`/perftest_c2c/matrix/runs/${runId}`);
  return {
    regions: response.data.regions,
    cells: response.data.cells,
  };
}

export async function getMatrixTrends(
  source: string,
  dest: string,
  testType: string,
  window?: number
): Promise<TrendPoint[]> {
  console.log('[c2c] getMatrixTrends { source:', source, ', dest:', dest, '}');
  const response = await apiClient.get<TrendsResponse>('/perftest_c2c/matrix/trends', {
    params: { source, dest, test_type: testType, ...(window && { window }) },
  });
  return response.data.trends;
}

export async function listRecurringJobs(): Promise<RecurringJob[]> {
  console.log('[c2c] listRecurringJobs');
  const response = await apiClient.get<RecurringJobsResponse>('/perftest_c2c/recurring');
  return response.data.jobs;
}

export async function createRecurringJob(payload: CreateRecurringPayload): Promise<RecurringJob> {
  console.log('[c2c] createRecurringJob { jobType:', payload.job_type, '}');
  const response = await apiClient.post<RecurringJob>('/perftest_c2c/recurring', payload);
  return response.data;
}

export async function deleteRecurringJob(jobId: string): Promise<void> {
  console.log('[c2c] deleteRecurringJob { jobId:', jobId, '}');
  await apiClient.delete(`/perftest_c2c/recurring/${jobId}`);
}

export async function updateRecurringJob(jobId: string, enabled: boolean): Promise<RecurringJob> {
  console.log('[c2c] updateRecurringJob { jobId:', jobId, ', enabled:', enabled, '}');
  const response = await apiClient.patch<{ enabled: boolean }>(`/perftest_c2c/recurring/${jobId}`, {
    enabled,
  });
  return { id: jobId, enabled: response.data.enabled } as RecurringJob;
}

export async function listRegions(): Promise<Region[]> {
  console.log('[c2c] listRegions');
  const response = await apiClient.get<RegionsResponse>('/perftest_c2c/regions');
  return response.data.regions;
}

export async function listVisibleNodes(region?: string): Promise<VisibleNode[]> {
  console.log('[c2c] listVisibleNodes { region:', region, '}');
  const response = await apiClient.get<NodesResponse>('/perftest_c2c/regions/nodes', {
    params: { ...(region && { region }) },
  });
  return response.data.nodes;
}
