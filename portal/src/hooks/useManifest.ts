import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface NavEntry {
  label: string;
  path: string;
  icon: string;
}

export interface ModuleManifest {
  name: string;
  nav: NavEntry[];
  flags: Record<string, boolean>;
}

export interface PortalManifest {
  modules: ModuleManifest[];
  role: string;
  meta?: Record<string, unknown>;
}

export function useManifest() {
  return useQuery<PortalManifest>({
    queryKey: ['manifest'],
    queryFn: async () => {
      console.log('[useManifest] Fetching manifest');
      const response = await apiClient.get<PortalManifest>('/portal/manifest');
      console.log(`[useManifest] Loaded ${response.data.modules.length} modules`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
