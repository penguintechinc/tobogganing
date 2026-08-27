import apiClient from './client';

/** Common response envelope metadata included on every netsvcs response. */
export interface ResponseMeta {
  version: number;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Zones
// ---------------------------------------------------------------------------

export interface Zone {
  id: string;
  name: string;
  visibility: string;
  description: string | null;
  created_at: string;
}

export interface ZonesResponse {
  zones: Zone[];
  meta: ResponseMeta;
}

export interface CreateZonePayload {
  name: string;
  visibility?: string;
  description?: string | null;
}

export interface UpdateZonePayload {
  name?: string;
  visibility?: string;
  description?: string | null;
}

// ---------------------------------------------------------------------------
// Zone records
// ---------------------------------------------------------------------------

export interface DnsRecord {
  id: string;
  name: string;
  type: string;
  value: string;
  ttl: number;
  created_at: string;
  priority: number | null;
  weight: number | null;
  port: number | null;
}

export interface RecordsResponse {
  records: DnsRecord[];
  meta: ResponseMeta;
}

export interface CreateRecordPayload {
  name: string;
  type: string;
  value: string;
  ttl?: number;
  priority?: number | null;
  weight?: number | null;
  port?: number | null;
}

export interface UpdateRecordPayload {
  name?: string;
  type?: string;
  value?: string;
  ttl?: number;
  priority?: number | null;
  weight?: number | null;
  port?: number | null;
}

// ---------------------------------------------------------------------------
// DNS servers
// ---------------------------------------------------------------------------

export interface DnsServer {
  id: string;
  name: string;
  status: string;
  version: string | null;
  region: string | null;
  hostname: string | null;
  last_heartbeat: string | null;
  created_at: string;
}

export interface DnsServersResponse {
  servers: DnsServer[];
  meta: ResponseMeta;
}

export interface DnsServerMetric {
  server_id: string;
  timestamp: string;
  queries_total: number;
  cache_hits: number;
  errors: number;
  avg_response_ms: number;
}

export interface DnsServerMetricsResponse {
  metrics: DnsServerMetric[];
  meta: ResponseMeta;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface QueryTimelineEntry {
  timestamp: string;
  queries: number;
}

export interface QueriesAnalytics {
  total_queries: number;
  total_cache_hits: number;
  total_errors: number;
  cache_hit_rate: number;
  timeline: QueryTimelineEntry[];
  meta: ResponseMeta;
}

export interface PerformanceMetric {
  metric: string;
  value: number;
}

export interface PerformanceAnalytics {
  metrics: PerformanceMetric[];
  meta: ResponseMeta;
}

export interface ServerSummaryEntry {
  server_id: string;
  server_name: string;
  queries: number;
  cache_hits: number;
  errors: number;
  avg_response_ms: number;
}

export interface ServersAnalytics {
  servers: ServerSummaryEntry[];
  meta: ResponseMeta;
}

export interface SummaryMetric {
  key: string;
  value: number;
}

export interface SummaryAnalytics {
  metrics: SummaryMetric[];
  meta: ResponseMeta;
}

export interface MessageResponse {
  message: string;
  meta: ResponseMeta;
}

// ---------------------------------------------------------------------------
// Zones API
// ---------------------------------------------------------------------------

/** List all DNS zones for the current tenant. */
export async function listZones(): Promise<Zone[]> {
  console.log('[netsvcs] listZones');
  const response = await apiClient.get<ZonesResponse>('/netsvcs/zones');
  return response.data.zones;
}

/** Create a new DNS zone. */
export async function createZone(payload: CreateZonePayload): Promise<Zone> {
  console.log('[netsvcs] createZone { name }', { name: payload.name });
  const response = await apiClient.post<Zone>('/netsvcs/zones', payload);
  return response.data;
}

/** Fetch a single zone by ID. */
export async function getZone(zoneId: string): Promise<Zone> {
  console.log('[netsvcs] getZone { zoneId }', { zoneId });
  const response = await apiClient.get<Zone>(`/netsvcs/zones/${zoneId}`);
  return response.data;
}

/** Update an existing DNS zone. */
export async function updateZone(zoneId: string, payload: UpdateZonePayload): Promise<Zone> {
  console.log('[netsvcs] updateZone { zoneId }', { zoneId });
  const response = await apiClient.put<Zone>(`/netsvcs/zones/${zoneId}`, payload);
  return response.data;
}

/** Delete a DNS zone and its records. */
export async function deleteZone(zoneId: string): Promise<MessageResponse> {
  console.log('[netsvcs] deleteZone { zoneId }', { zoneId });
  const response = await apiClient.delete<MessageResponse>(`/netsvcs/zones/${zoneId}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Records API
// ---------------------------------------------------------------------------

/** List all records within a zone. */
export async function listRecords(zoneId: string): Promise<DnsRecord[]> {
  console.log('[netsvcs] listRecords { zoneId }', { zoneId });
  const response = await apiClient.get<RecordsResponse>(`/netsvcs/zones/${zoneId}/records`);
  return response.data.records;
}

/** Create a new record within a zone. */
export async function createRecord(
  zoneId: string,
  payload: CreateRecordPayload
): Promise<DnsRecord> {
  console.log('[netsvcs] createRecord { zoneId, name }', { zoneId, name: payload.name });
  const response = await apiClient.post<DnsRecord>(`/netsvcs/zones/${zoneId}/records`, payload);
  return response.data;
}

/** Update an existing record within a zone. */
export async function updateRecord(
  zoneId: string,
  recordId: string,
  payload: UpdateRecordPayload
): Promise<DnsRecord> {
  console.log('[netsvcs] updateRecord { zoneId, recordId }', { zoneId, recordId });
  const response = await apiClient.put<DnsRecord>(
    `/netsvcs/zones/${zoneId}/records/${recordId}`,
    payload
  );
  return response.data;
}

/** Delete a record from a zone. */
export async function deleteRecord(zoneId: string, recordId: string): Promise<MessageResponse> {
  console.log('[netsvcs] deleteRecord { zoneId, recordId }', { zoneId, recordId });
  const response = await apiClient.delete<MessageResponse>(
    `/netsvcs/zones/${zoneId}/records/${recordId}`
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// DNS servers API
// ---------------------------------------------------------------------------

/** List all DNS resolver servers for the current tenant. */
export async function listDnsServers(): Promise<DnsServer[]> {
  console.log('[netsvcs] listDnsServers');
  const response = await apiClient.get<DnsServersResponse>('/netsvcs/dns-servers');
  return response.data.servers;
}

/** Fetch a single DNS resolver server by ID. */
export async function getDnsServer(serverId: string): Promise<DnsServer> {
  console.log('[netsvcs] getDnsServer { serverId }', { serverId });
  const response = await apiClient.get<DnsServer>(`/netsvcs/dns-servers/${serverId}`);
  return response.data;
}

/** Delete a DNS resolver server and its metrics history. */
export async function deleteDnsServer(serverId: string): Promise<MessageResponse> {
  console.log('[netsvcs] deleteDnsServer { serverId }', { serverId });
  const response = await apiClient.delete<MessageResponse>(`/netsvcs/dns-servers/${serverId}`);
  return response.data;
}

/** Fetch recent metrics for a DNS resolver server (default lookback: 24h). */
export async function getDnsServerMetrics(
  serverId: string,
  hours = 24
): Promise<DnsServerMetric[]> {
  console.log('[netsvcs] getDnsServerMetrics { serverId, hours }', { serverId, hours });
  const response = await apiClient.get<DnsServerMetricsResponse>(
    `/netsvcs/dns-servers/${serverId}/metrics`,
    { params: { hours } }
  );
  return response.data.metrics;
}

// ---------------------------------------------------------------------------
// Analytics API
// ---------------------------------------------------------------------------

/** Fetch tenant-scoped dashboard summary counts (zones/records/servers/queries). */
export async function getAnalyticsSummary(): Promise<SummaryMetric[]> {
  console.log('[netsvcs] getAnalyticsSummary');
  const response = await apiClient.get<SummaryAnalytics>('/netsvcs/analytics/summary');
  return response.data.metrics;
}

/** Fetch query volume + cache-hit analytics with an hourly timeline. */
export async function getAnalyticsQueries(hours = 24): Promise<QueriesAnalytics> {
  console.log('[netsvcs] getAnalyticsQueries { hours }', { hours });
  const response = await apiClient.get<QueriesAnalytics>('/netsvcs/analytics/queries', {
    params: { hours },
  });
  return response.data;
}

/** Fetch response-time performance metrics (avg/min/max/percentiles). */
export async function getAnalyticsPerformance(hours = 24): Promise<PerformanceMetric[]> {
  console.log('[netsvcs] getAnalyticsPerformance { hours }', { hours });
  const response = await apiClient.get<PerformanceAnalytics>('/netsvcs/analytics/performance', {
    params: { hours },
  });
  return response.data.metrics;
}

/** Fetch per-server analytics breakdown. */
export async function getAnalyticsServers(hours = 24): Promise<ServerSummaryEntry[]> {
  console.log('[netsvcs] getAnalyticsServers { hours }', { hours });
  const response = await apiClient.get<ServersAnalytics>('/netsvcs/analytics/servers', {
    params: { hours },
  });
  return response.data.servers;
}
