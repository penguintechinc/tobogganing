import apiClient from './client';

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
