import apiClient from './client';

// Cluster / Client / Status types
export interface Cluster {
  id: string;
  name: string;
  region: string;
  datacenter: string;
  status: string;
  client_count: number;
}

export interface ClustersResponse {
  clusters: Cluster[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface Client {
  id: string;
  name: string;
  type: string;
  cluster_id: string;
  status: string;
  last_seen: string;
}

export interface ClientsResponse {
  clients: Client[];
  meta: {
    version: number;
    timestamp: string;
  };
}

export interface StatusMetrics {
  total: number;
  active: number;
}

export interface StatusData {
  service: string;
  status: string;
  clusters: StatusMetrics;
  clients: StatusMetrics;
  meta: {
    version: number;
    timestamp: string;
  };
}

// Block Pages types
export interface BlockPage {
  id: string;
  tenant: string;
  name: string;
  markdown: string;
  status: 'draft' | 'live';
  version: number;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface BlockPagePreview {
  html: string;
  variables: Record<string, string>;
}

// Block Routes types
export interface BlockRoute {
  id: string;
  tenant: string;
  source_type: string;
  destination_kind: 'page' | 'external';
  page_id: string | null;
  external_url: string | null;
  created_at: string;
  created_by: string | null;
  updated_by: string | null;
  ticket: string | null;
  notes: string | null;
  expiry: string | null;
  review_date: string | null;
  scope: string | null;
  risk: string | null;
}

export interface BlockRouteMetadata {
  created_by?: string;
  updated_by?: string;
  ticket?: string;
  notes?: string;
  expiry?: string;
  review_date?: string;
  scope?: string;
  risk?: string;
}

// Existing API functions
export async function listClusters(): Promise<Cluster[]> {
  console.log('[sase] listClusters');
  const response = await apiClient.get<ClustersResponse>('/sdwan/clusters');
  return response.data.clusters;
}

export async function listClients(): Promise<Client[]> {
  console.log('[sase] listClients');
  const response = await apiClient.get<ClientsResponse>('/sdwan/clients');
  return response.data.clients;
}

export async function getStatus(): Promise<StatusData> {
  console.log('[sase] getStatus');
  const response = await apiClient.get<StatusData>('/sdwan/status');
  return response.data;
}

// Block Pages API functions
export async function listBlockPages(): Promise<BlockPage[]> {
  console.log('[BlockPages] listBlockPages');
  const response = await apiClient.get<{ pages: BlockPage[] }>('/blockpages/pages');
  return response.data.pages;
}

export async function createBlockPage(name: string, markdown: string): Promise<BlockPage> {
  console.log('[BlockPages] createBlockPage { name }', { name });
  const response = await apiClient.post<BlockPage>('/blockpages/pages', {
    name,
    markdown,
  });
  return response.data;
}

export async function updateBlockPage(pageId: string, markdown: string): Promise<BlockPage> {
  console.log('[BlockPages] updateBlockPage { pageId }', { pageId });
  const response = await apiClient.put<BlockPage>(`/blockpages/pages/${pageId}`, {
    markdown,
  });
  return response.data;
}

export async function publishBlockPage(pageId: string): Promise<BlockPage> {
  console.log('[BlockPages] publishBlockPage { pageId }', { pageId });
  const response = await apiClient.post<BlockPage>(`/blockpages/pages/${pageId}/publish`);
  return response.data;
}

export async function previewBlockPage(
  pageId: string,
  variables?: Record<string, string>
): Promise<BlockPagePreview> {
  console.log('[BlockPages] previewBlockPage { pageId }', { pageId });
  const response = await apiClient.post<BlockPagePreview>(
    `/blockpages/pages/${pageId}/preview`,
    { variables: variables || {} }
  );
  return response.data;
}

// Block Routes API functions
export async function listBlockRoutes(): Promise<BlockRoute[]> {
  console.log('[BlockRoutes] listBlockRoutes');
  const response = await apiClient.get<{ routes: BlockRoute[] }>('/blockpages/routes');
  return response.data.routes;
}

export async function upsertBlockRoutes(
  routes: Array<{
    source_type: string;
    destination_kind: 'page' | 'external';
    page_id?: string | null;
    external_url?: string | null;
    metadata?: BlockRouteMetadata;
  }>
): Promise<BlockRoute[]> {
  console.log('[BlockRoutes] upsertBlockRoutes { count }', { count: routes.length });
  const response = await apiClient.put<{ routes: BlockRoute[] }>('/blockpages/routes', {
    routes,
  });
  return response.data.routes;
}
