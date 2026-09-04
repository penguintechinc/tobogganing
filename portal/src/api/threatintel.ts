import apiClient from './client';

/** Common response envelope metadata included on every threatintel response. */
export interface ResponseMeta {
  version: number;
  timestamp: string;
  total?: number;
  limit?: number;
  offset?: number;
}

export interface MessageResponse {
  message: string;
  meta: ResponseMeta;
}

// ---------------------------------------------------------------------------
// Feeds
// ---------------------------------------------------------------------------

export const FEED_SOURCE_TYPES = ['misp', 'stix', 'taxii', 'csv'] as const;
export type FeedSourceType = (typeof FEED_SOURCE_TYPES)[number];

export interface FeedSource {
  id: string;
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
  last_refresh_error: string | null;
  created_at: string;
}

export interface FeedSourcesResponse {
  sources: FeedSource[];
  meta: ResponseMeta;
}

export interface CreateFeedSourcePayload {
  name: string;
  source_type: string;
  url: string;
  enabled?: boolean;
}

export interface RefreshFeedResult {
  id: string;
  status: string;
  added: number;
  updated: number;
  errors: number;
  meta: ResponseMeta;
}

/** List all threat-intel feed sources for the current tenant. */
export async function listFeeds(): Promise<FeedSource[]> {
  console.log('[threatintel] listFeeds');
  const response = await apiClient.get<FeedSourcesResponse>('/threatintel/feeds');
  return response.data.sources;
}

/** Create a new threat-intel feed source. */
export async function createFeed(payload: CreateFeedSourcePayload): Promise<FeedSource> {
  console.log('[threatintel] createFeed { name, source_type }', {
    name: payload.name,
    source_type: payload.source_type,
  });
  const response = await apiClient.post<FeedSource>('/threatintel/feeds', payload);
  return response.data;
}

/** Delete a threat-intel feed source. */
export async function deleteFeed(feedId: string): Promise<MessageResponse> {
  console.log('[threatintel] deleteFeed { feedId }', { feedId });
  const response = await apiClient.delete<MessageResponse>(`/threatintel/feeds/${feedId}`);
  return response.data;
}

/** Trigger an immediate ingest refresh for a threat-intel feed source. */
export async function refreshFeed(feedId: string): Promise<RefreshFeedResult> {
  console.log('[threatintel] refreshFeed { feedId }', { feedId });
  const response = await apiClient.post<RefreshFeedResult>(`/threatintel/feeds/${feedId}/refresh`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Blocklist
// ---------------------------------------------------------------------------

export const IOC_TYPES = ['ip', 'domain', 'url', 'hash'] as const;
export type IocType = (typeof IOC_TYPES)[number];

export interface BlocklistEntry {
  id: string;
  indicator_type: string;
  value: string;
  source: string;
  confidence: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BlocklistEntriesResponse {
  entries: BlocklistEntry[];
  meta: ResponseMeta;
}

export interface CreateBlocklistEntryPayload {
  indicator_type: string;
  value: string;
  source?: string;
  confidence?: number;
  ttl?: number;
}

export interface BlocklistFilters {
  indicator_type?: string;
  source?: string;
  limit?: number;
  offset?: number;
}

/** List blocklist entries for the tenant, with optional type/source filters. */
export async function listBlocklist(filters: BlocklistFilters = {}): Promise<BlocklistEntry[]> {
  console.log('[threatintel] listBlocklist { filters }', { filters });
  const response = await apiClient.get<BlocklistEntriesResponse>('/threatintel/blocklist', {
    params: filters,
  });
  return response.data.entries;
}

/** Add a manual blocklist entry for the tenant. */
export async function addBlocklistEntry(
  payload: CreateBlocklistEntryPayload
): Promise<BlocklistEntry> {
  console.log('[threatintel] addBlocklistEntry { indicator_type }', {
    indicator_type: payload.indicator_type,
  });
  const response = await apiClient.post<BlocklistEntry>('/threatintel/blocklist', payload);
  return response.data;
}

/** Remove a blocklist entry for the tenant. */
export async function deleteBlocklistEntry(entryId: string): Promise<MessageResponse> {
  console.log('[threatintel] deleteBlocklistEntry { entryId }', { entryId });
  const response = await apiClient.delete<MessageResponse>(`/threatintel/blocklist/${entryId}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// IOC check
// ---------------------------------------------------------------------------

export interface IocVerdict {
  ioc_type: string;
  value: string;
  severity: string;
  source: string;
  stix_id: string;
  first_seen: number;
  expiry: number | null;
}

/**
 * Check whether an indicator is present in the SASE blocklist. Resolves to
 * `null` when the backend reports 404 (not found) rather than throwing, so
 * callers can render a clean "not blocked" verdict; all other errors
 * (network, 400 invalid type, 500) propagate for the caller to handle.
 */
export async function checkIoc(iocType: string, value: string): Promise<IocVerdict | null> {
  console.log('[threatintel] checkIoc { iocType }', { iocType });
  try {
    const response = await apiClient.get<IocVerdict>('/threatintel/blocklist/check', {
      params: { type: iocType, value },
    });
    return response.data;
  } catch (err) {
    const status = (err as { response?: { status?: number } }).response?.status;
    if (status === 404) {
      return null;
    }
    throw err;
  }
}
