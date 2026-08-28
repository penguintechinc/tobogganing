import apiClient from './client';

/** Alert Rules */
export interface AlertRule {
  id: string;
  name: string;
  metric: string;
  comparator: 'gt' | 'gte' | 'lt' | 'lte';
  threshold: number;
  window_seconds: number;
  device_id?: string;
  test_type?: string;
  channel_id?: string;
  enabled: boolean;
  created_at: string;
}

export interface AlertRulesResponse {
  rules: AlertRule[];
  meta: { version: number; timestamp: string };
}

/** Alert Events */
export interface AlertEvent {
  id: string;
  rule_id: string;
  device_id: string;
  observed_value: number;
  fired_at: string;
  notified: boolean;
}

export interface AlertEventsResponse {
  events: AlertEvent[];
  meta: { version: number; timestamp: string };
}

/** Alert Channels */
export interface AlertChannel {
  id: string;
  name: string;
  kind: 'email' | 'webhook';
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
}

export interface AlertChannelsResponse {
  channels: AlertChannel[];
  meta: { version: number; timestamp: string };
}

/** Scheduled Tests */
export interface ScheduledTest {
  id: string;
  device_id: string;
  test_type: string;
  target: string;
  interval_seconds: number;
  enabled: boolean;
  next_run_at: string;
  last_run_at?: string | null;
  created_at: string;
}

export interface ScheduledTestsResponse {
  jobs: ScheduledTest[];
  meta: { version: number; timestamp: string };
}

/** AutoPerf Policies */
export interface AutoPerfPolicy {
  id: string;
  tenant: string;
  name: string;
  device_id: string;
  target: string;
  t1_interval_seconds: number;
  t2_interval_seconds: number;
  t3_interval_seconds: number;
  deescalate_after_clean: number;
  enabled: boolean;
  created_at: string;
}

export interface AutoPerfState {
  current_tier: 'T1' | 'T2' | 'T3';
  clean_cycles: number;
  escalated_at?: string | null;
}

/** AutoCheckIn */
export interface AutoCheckIn {
  id: string;
  tenant: string;
  name: string;
  device_id: string;
  target_kind: 'ours' | 'external';
  target: string;
  test_types: string[];
  interval_minutes: number;
  jitter_pct: number;
  samples_per_run: number;
  threshold_stddev_min: number | null;
  threshold_stddev_max: number | null;
  threshold_mean: number | null;
  tier: number;
  parent_checkin_id: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutoCheckInState {
  checkin_id: string;
  last_breached: boolean;
  last_mean_latency_ms: number | null;
  last_stddev_latency_ms: number | null;
  last_run_at: string | null;
  updated_at: string;
}

/** API Functions - Alerts */
export async function listAlertRules(): Promise<AlertRule[]> {
  console.log('[wpcOps] listAlertRules');
  const response = await apiClient.get<AlertRulesResponse>('/perftest_cluster/alerts/rules');
  return response.data.rules;
}

export async function createAlertRule(payload: {
  name: string;
  metric: string;
  comparator: string;
  threshold: number;
  window_seconds?: number;
  device_id?: string;
  test_type?: string;
  channel_id?: string;
  enabled?: boolean;
}): Promise<AlertRule> {
  console.log('[wpcOps] createAlertRule { metric:', payload.metric, '}');
  const response = await apiClient.post<AlertRule>('/perftest_cluster/alerts/rules', payload);
  return response.data;
}

export async function deleteAlertRule(ruleId: string): Promise<void> {
  console.log('[wpcOps] deleteAlertRule { rule_id:', ruleId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/alerts/rules/${ruleId}`);
}

export async function listAlertEvents(): Promise<AlertEvent[]> {
  console.log('[wpcOps] listAlertEvents');
  const response = await apiClient.get<AlertEventsResponse>('/perftest_cluster/alerts/events');
  return response.data.events;
}

export async function listAlertChannels(): Promise<AlertChannel[]> {
  console.log('[wpcOps] listAlertChannels');
  const response = await apiClient.get<AlertChannelsResponse>('/perftest_cluster/alerts/channels');
  return response.data.channels;
}

export async function createAlertChannel(payload: {
  name: string;
  kind: 'email' | 'webhook';
  config: Record<string, unknown>;
  enabled?: boolean;
}): Promise<AlertChannel> {
  console.log('[wpcOps] createAlertChannel { kind:', payload.kind, '}');
  const response = await apiClient.post<AlertChannel>('/perftest_cluster/alerts/channels', payload);
  return response.data;
}

export async function deleteAlertChannel(channelId: string): Promise<void> {
  console.log('[wpcOps] deleteAlertChannel { channel_id:', channelId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/alerts/channels/${channelId}`);
}

/** API Functions - Scheduled Tests */
export async function listScheduledTests(): Promise<ScheduledTest[]> {
  console.log('[wpcOps] listScheduledTests');
  const response = await apiClient.get<ScheduledTestsResponse>('/perftest_cluster/scheduled-tests');
  return response.data.jobs;
}

export async function createScheduledTest(payload: {
  device_id: string;
  test_type: string;
  target: string;
  interval_seconds: number;
}): Promise<ScheduledTest> {
  console.log('[wpcOps] createScheduledTest { device_id:', payload.device_id, '}');
  const response = await apiClient.post<ScheduledTest>(
    '/perftest_cluster/scheduled-tests',
    payload
  );
  return response.data;
}

export async function updateScheduledTest(
  jobId: string,
  payload: { enabled: boolean }
): Promise<ScheduledTest> {
  console.log('[wpcOps] updateScheduledTest { job_id:', jobId.slice(0, 8), '}');
  const response = await apiClient.patch<ScheduledTest>(
    `/perftest_cluster/scheduled-tests/${jobId}`,
    payload
  );
  return response.data;
}

export async function deleteScheduledTest(jobId: string): Promise<void> {
  console.log('[wpcOps] deleteScheduledTest { job_id:', jobId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/scheduled-tests/${jobId}`);
}

/** API Functions - AutoPerf */
export async function listAutoPerfPolicies(): Promise<AutoPerfPolicy[]> {
  console.log('[wpcOps] listAutoPerfPolicies');
  const response = await apiClient.get<{ policies: AutoPerfPolicy[] }>(
    '/perftest_cluster/autoperf/policies'
  );
  return response.data.policies;
}

export async function createAutoPerfPolicy(payload: {
  name: string;
  device_id: string;
  target: string;
  t1_interval_seconds?: number;
  t2_interval_seconds?: number;
  t3_interval_seconds?: number;
  deescalate_after_clean?: number;
  enabled?: boolean;
}): Promise<AutoPerfPolicy> {
  console.log('[wpcOps] createAutoPerfPolicy { name:', payload.name, '}');
  const response = await apiClient.post<AutoPerfPolicy>(
    '/perftest_cluster/autoperf/policies',
    payload
  );
  return response.data;
}

export async function deleteAutoPerfPolicy(policyId: string): Promise<void> {
  console.log('[wpcOps] deleteAutoPerfPolicy { policy_id:', policyId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/autoperf/policies/${policyId}`);
}

export async function getAutoPerfPolicyState(policyId: string): Promise<AutoPerfState> {
  console.log('[wpcOps] getAutoPerfPolicyState { policy_id:', policyId.slice(0, 8), '}');
  const response = await apiClient.get<AutoPerfState>(
    `/perftest_cluster/autoperf/policies/${policyId}/state`
  );
  return response.data;
}
/** API Functions - AutoCheckIn */
export async function listAutoCheckIns(): Promise<AutoCheckIn[]> {
  console.log('[wpcOps] listAutoCheckIns');
  const response = await apiClient.get<{ checkins: AutoCheckIn[] }>(
    '/perftest_cluster/auto-checkins'
  );
  return response.data.checkins;
}

export async function createAutoCheckIn(payload: {
  name: string;
  device_id: string;
  target_kind: 'ours' | 'external';
  target: string;
  test_types?: string[];
  interval_minutes?: number;
  jitter_pct?: number;
  samples_per_run?: number;
  threshold_stddev_min?: number;
  threshold_stddev_max?: number;
  threshold_mean?: number;
  tier?: number;
  parent_checkin_id?: string;
  enabled?: boolean;
}): Promise<AutoCheckIn> {
  console.log('[wpcOps] createAutoCheckIn { name:', payload.name, '}');
  const response = await apiClient.post<AutoCheckIn>('/perftest_cluster/auto-checkins', payload);
  return response.data;
}

export async function updateAutoCheckIn(
  checkinId: string,
  payload: Partial<
    Pick<
      AutoCheckIn,
      | 'name'
      | 'target'
      | 'test_types'
      | 'interval_minutes'
      | 'jitter_pct'
      | 'samples_per_run'
      | 'threshold_stddev_min'
      | 'threshold_stddev_max'
      | 'threshold_mean'
      | 'enabled'
    >
  >
): Promise<AutoCheckIn> {
  console.log('[wpcOps] updateAutoCheckIn { checkin_id:', checkinId.slice(0, 8), '}');
  const response = await apiClient.patch<AutoCheckIn>(
    `/perftest_cluster/auto-checkins/${checkinId}`,
    payload
  );
  return response.data;
}

export async function deleteAutoCheckIn(checkinId: string): Promise<void> {
  console.log('[wpcOps] deleteAutoCheckIn { checkin_id:', checkinId.slice(0, 8), '}');
  await apiClient.delete(`/perftest_cluster/auto-checkins/${checkinId}`);
}

export async function getAutoCheckInState(checkinId: string): Promise<AutoCheckInState> {
  console.log('[wpcOps] getAutoCheckInState { checkin_id:', checkinId.slice(0, 8), '}');
  const response = await apiClient.get<AutoCheckInState>(
    `/perftest_cluster/auto-checkins/${checkinId}/state`
  );
  return response.data;
}
